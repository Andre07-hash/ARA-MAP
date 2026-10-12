"""R3-A1: batched attachment summaries for one page of terrains.

`archivos.resumenes_de_archivos` used to authorize and summarize terrain by
terrain (8 statements each). These tests pin the batched version to the old
behavior: the old algorithm is kept here verbatim as the reference, and both
are run over the same synthetic fixture on SQLite and on a disposable
Postgres schema. They compare every output (keys, order, values) and every
error (status and code) across accounts, scopes, sessions and inputs, check
the privacy projections explicitly, and count statements per page size.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from server import archivos, auth, db, postgres
from server.errors import ApiError
from server.repo import archivos as repo
from server.repo import maestra
from tests.support import TEST_PASSWORD

URL = os.environ.get("ARA_MAP_TEST_DATABASE_URL")
AHORA = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def iso(minutos: int) -> str:
    return (AHORA + timedelta(minutes=minutos)).isoformat()


# -- the reference: the per-terrain algorithm before R3-A1, verbatim -------------

def resumenes_anteriores(conn, inventory_ids, sesion, now) -> dict[str, Any]:
    if not isinstance(sesion, auth.Sesion):
        raise auth.no_autenticado()
    authorized: list[str] = []
    unavailable: list[str] = []
    seen: set[str] = set()
    for terrain_id in inventory_ids:
        if terrain_id in seen:
            continue
        seen.add(terrain_id)
        try:
            auth.require_terreno(SimpleNamespace(sesion=sesion), terrain_id, "archivos.ver", conn)
        except ApiError as exc:
            if exc.status == 404:
                unavailable.append(terrain_id)
                continue
            raise
        authorized.append(terrain_id)
    output: dict[str, dict[str, Any]] = {}
    for terrain_id in authorized:
        pdf_rows = conn.execute(
            "SELECT a.*, " + repo._LATEST_VERSION + " WHERE a.inventory_id = ? AND a.tipo = 'pdf'"
            " AND a.retirado_en IS NULL ORDER BY a.creado_en DESC, a.id DESC LIMIT 5",
            (now, terrain_id)).fetchall()
        kmz = conn.execute(
            "SELECT a.*, " + repo._LATEST_VERSION + " WHERE a.inventory_id = ? AND a.tipo = 'kmz'"
            " AND a.retirado_en IS NULL LIMIT 1", (now, terrain_id)).fetchone()
        output[terrain_id] = {
            "pdf_total": int(conn.execute("SELECT COUNT(*) AS n FROM archivo WHERE inventory_id = ?"
                                          " AND tipo = 'pdf' AND retirado_en IS NULL",
                                          (terrain_id,)).fetchone()["n"]),
            "pdf_recientes": [repo._summary_row(r, sesion.user_id, now) for r in pdf_rows],
            "kmz": repo._summary_row(kmz, sesion.user_id, now) if kmz else None,
        }
    return {"resultados": output, "no_disponibles": unavailable}


class Contador:
    """A connection that counts the statements sent through it."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self.sentencias = 0

    def execute(self, *args, **kwargs):
        self.sentencias += 1
        return self._conn.execute(*args, **kwargs)

    def __getattr__(self, nombre):
        return getattr(self._conn, nombre)


def resultado(fn) -> tuple[str, Any]:
    """The value, or the error as (status, code): what a caller can observe."""
    try:
        return "ok", fn()
    except ApiError as exc:
        return "error", (exc.status, (exc.detalle or {}).get("code"))


class ResumenesLote:
    database: Path | None = None

    # -- fixture ------------------------------------------------------------------

    def setUp(self) -> None:
        self.prepare_database()
        with db.session(self.database) as conn:
            self.cuentas = {login: auth.create_user(conn, login, f"{login.capitalize()} Ficticia",
                                                    TEST_PASSWORD, iterations=1000, rol=rol)
                            for login, rol in (("ana", "admin"), ("olga", "operador"),
                                         ("omar", "operador"), ("otto", "operador"),
                                               ("ines", "operador"))}
            self.u = {login: cuenta["id"] for login, cuenta in self.cuentas.items()}
            self.tokens = {}
            for login in self.u:
                token, _, _ = auth.login(conn, login, TEST_PASSWORD)
                self.tokens[login] = token
            self.s = {login: auth.sesion_de_token(conn, t) for login, t in self.tokens.items()}
            self.base_a = maestra.crear(conn, "Base Ficticia A", self.cuentas["ana"])["id"]
            self.base_b = maestra.crear(conn, "Base Ficticia B", self.cuentas["ana"])["id"]
            self.base_c = maestra.crear(conn, "Base Ficticia C archivada", self.cuentas["ana"])["id"]
            for base, login in ((self.base_a, "olga"), (self.base_a, "omar"), (self.base_b, "omar"),
                                (self.base_c, "olga"), (self.base_a, "ines")):
                conn.execute("INSERT INTO maestra_base_acceso (base_id, user_id, granted_at, granted_by)"
                             " VALUES (?, ?, ?, ?)", (base, self.u[login], iso(-500), self.u["ana"]))
            conn.execute("UPDATE maestra_base SET archived_at = ? WHERE id = ?", (iso(-400), self.base_c))
            self.t = {nombre: self._terreno(conn, base) for nombre, base in (
                ("a1", self.base_a), ("a2", self.base_a), ("a3", self.base_a), ("a_archivado", self.base_a),
                ("b1", self.base_b), ("c1", self.base_c), ("sin_base", None))}
            conn.execute("UPDATE inventory_terrain SET archived_at = ? WHERE id = ?",
                         (iso(-300), self.t["a_archivado"]))
            self._archivos(conn)

    def prepare_database(self) -> None:
        raise NotImplementedError

    def _terreno(self, conn, base_id) -> str:
        tid = str(uuid.uuid4())
        conn.execute("INSERT INTO inventory_terrain (id, version, base_id, created_at, created_by,"
                     " updated_at, updated_by) VALUES (?, 1, ?, ?, ?, ?, ?)",
                     (tid, base_id, iso(-600), self.u["ana"], iso(-600), self.u["ana"]))
        return tid

    def _archivo(self, conn, terreno, tipo, creado, *, retirado=False, id_=None) -> str:
        aid = id_ or str(uuid.uuid4())
        conn.execute(
            "INSERT INTO archivo (id, inventory_id, columna_id, tipo, revision, retirado_en, retirado_por,"
            " retirado_motivo, creado_en, creado_por, actualizado_en, actualizado_por)"
            " VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
            (aid, terreno, "core:archivos" if tipo == "pdf" else "core:kmz", tipo,
             iso(-10) if retirado else None, self.u["ana"] if retirado else None,
             "usuario" if retirado else None, creado, self.u["ana"], creado, self.u["ana"]))
        return aid

    def _version(self, conn, archivo, terreno, numero, estado, *, por="ana", completar=60,
                 lease=None, nombre=None) -> str:
        vid = str(uuid.uuid4())
        terminal = estado != "subiendo"
        final = estado in ("disponible", "fallido")
        conn.execute(
            "INSERT INTO archivo_version (id, archivo_id, inventory_id, numero, estado, revision_base,"
            " nombre_original, tamano_declarado, sha256_declarado, tamano, sha256, clave_temporal,"
            " clave_final, subida_vence_en, completar_antes_de, error_codigo, error_mensaje, aplicada,"
            " iniciado_en, iniciado_por, finalizado_en, finalizado_por, terminado_en, terminado_por)"
            " VALUES (?, ?, ?, ?, ?, 1, ?, 10, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, archivo, terreno, numero, estado, nombre or f"Privado {vid[:8]}.pdf", "a" * 64,
             10 if estado == "disponible" else None, "b" * 64 if estado == "disponible" else None,
             f"temporal/{vid}", f"final/{vid}" if estado == "disponible" else None,
             iso(completar - 30), iso(completar),
             "sha256_no_coincide" if estado == "fallido" else None,
             "No coincide." if estado == "fallido" else None,
             (1 if estado == "disponible" else 0) if final else None,
             iso(-50), self.u[por], iso(-40) if final else None, self.u[por] if final else None,
             iso(-40) if terminal else None, self.u[por] if terminal else None))
        if lease is not None:
            conn.execute("INSERT INTO archivo_trabajo (archivo_version_id, trabajo_id, actor_id, operacion,"
                         " inicio, vence_en) VALUES (?, ?, ?, 'completar', ?, ?)",
                         (vid, str(uuid.uuid4()), self.u[por], iso(-1), iso(lease)))
        return vid

    def _archivos(self, conn) -> None:
        a1 = self.t["a1"]
        # Seven live PDFs (two share a creation time: id breaks the tie), plus
        # two retired ones that are newer than all of them.
        estados = [("disponible", {}), ("subiendo", {"por": "olga"}),            # own pending for olga
                   ("subiendo", {"por": "omar", "completar": -5}),               # overdue, no lease: expirado
                   ("subiendo", {"por": "ana", "completar": -5, "lease": 10}),   # overdue, live lease
                   ("fallido", {}), ("cancelado", {}), ("disponible", {})]
        for i, (estado, extra) in enumerate(estados):
            creado = iso(-100 + (i if i != 3 else 2))                            # 2 and 3 tie
            aid = self._archivo(conn, a1, "pdf", creado)
            if i % 2 == 0:
                self._version(conn, aid, a1, 1, "disponible")
                self._version(conn, aid, a1, 2, estado, **extra)
            else:
                self._version(conn, aid, a1, 1, estado, **extra)
        for _ in range(2):
            aid = self._archivo(conn, a1, "pdf", iso(-1), retirado=True)
            self._version(conn, aid, a1, 1, "disponible")
        kmz = self._archivo(conn, a1, "kmz", iso(-90))
        vid = self._version(conn, kmz, a1, 1, "disponible", nombre="Contorno ficticio.kmz")
        conn.execute("UPDATE archivo SET version_actual_id = ? WHERE id = ?", (vid, kmz))
        # a2: a retired KMZ, and a live one whose replacement is another account's.
        viejo = self._archivo(conn, self.t["a2"], "kmz", iso(-200), retirado=True)
        self._version(conn, viejo, self.t["a2"], 1, "disponible")
        vivo = self._archivo(conn, self.t["a2"], "kmz", iso(-80))
        self._version(conn, vivo, self.t["a2"], 1, "disponible")
        self._version(conn, vivo, self.t["a2"], 2, "subiendo", por="omar", nombre="Secreto ficticio.kmz")
        # a3 has nothing. The others have one PDF each, one with no version at all.
        for nombre in ("a_archivado", "b1", "c1", "sin_base"):
            aid = self._archivo(conn, self.t[nombre], "pdf", iso(-70))
            self._version(conn, aid, self.t[nombre], 1, "disponible")
        self._archivo(conn, self.t["b1"], "pdf", iso(-60))

    # -- helpers ------------------------------------------------------------------

    def nuevo(self, conn, ids, sesion):
        return archivos.resumenes_de_archivos(conn, ids, sesion, reloj=lambda: AHORA)

    def anterior(self, conn, ids, sesion):
        return resumenes_anteriores(conn, ids, sesion, AHORA.isoformat())

    def assert_equivalente(self, ids, sesion, mensaje=""):
        with db.session(self.database) as conn:
            antes = resultado(lambda: self.anterior(conn, list(ids), sesion))
            despues = resultado(lambda: self.nuevo(conn, list(ids), sesion))
        self.assertEqual(despues, antes, mensaje)
        if antes[0] == "ok":
            # Same order too: dicts compare equal regardless of insertion order.
            self.assertEqual(list(despues[1]["resultados"]), list(antes[1]["resultados"]), mensaje)
        return despues

    def entradas(self) -> dict[str, list]:
        todos = list(self.t.values())
        falta = str(uuid.uuid4())
        return {
            "vacia": [],
            "una": [self.t["a1"]],
            "todas": todos,
            "al_reves": list(reversed(todos)),
            "duplicadas": [self.t["a1"], self.t["b1"], self.t["a1"], self.t["b1"], self.t["a2"]],
            "inexistentes_y_malformadas": [falta, self.t["a1"], "no-es-uuid", "", falta, "' OR 1=1 --"],
            "solo_ajenas": [self.t["c1"], self.t["sin_base"], falta],
        }

    # -- equivalence ----------------------------------------------------------------

    def test_same_output_and_order_for_every_account_and_input(self):
        for login, sesion in self.s.items():
            for nombre, ids in self.entradas().items():
                with self.subTest(cuenta=login, entrada=nombre):
                    self.assert_equivalente(ids, sesion)

    def test_invalid_sessions_fail_the_same_way_and_empty_input_stays_empty(self):
        with db.escritura(self.database) as conn:
            conn.execute("UPDATE team_session SET revoked_at = ? WHERE token_hash = ?",
                         (iso(0), self.s["olga"].referencia))
            conn.execute("UPDATE team_session SET expires_at = ? WHERE token_hash = ?",
                         (time.time() - 5, self.s["omar"].referencia))
            conn.execute("UPDATE team_user SET active = 0 WHERE id = ?", (self.u["otto"],))
            conn.execute("UPDATE team_user SET credential_revision = credential_revision + 1"
                         " WHERE id = ?", (self.u["ines"],))
        for login in ("olga", "omar", "otto", "ines"):
            for nombre, ids in self.entradas().items():
                with self.subTest(cuenta=login, entrada=nombre):
                    r = self.assert_equivalente(ids, self.s[login])
                    self.assertEqual(r, ("ok", {"resultados": {}, "no_disponibles": []}) if not ids
                                     else ("error", (401, "unauthenticated")))
        with db.session(self.database) as conn:
            for valor in (None, "token", {"user_id": self.u["ana"]}):
                with self.subTest(sesion=repr(valor)):
                    self.assertEqual(resultado(lambda: self.nuevo(conn, [self.t["a1"]], valor)),
                                     resultado(lambda: self.anterior(conn, [self.t["a1"]], valor)))

    def test_a_role_without_the_read_capability_is_refused_the_same_way(self):
        sin = {**auth.CAPACIDADES, "operador": tuple(c for c in auth.CAPACIDADES["operador"]
                                                   if c != "archivos.ver")}
        with patch.dict(auth.CAPACIDADES, sin):
            for nombre, ids in self.entradas().items():
                with self.subTest(entrada=nombre):
                    r = self.assert_equivalente(ids, self.s["olga"])
                    if ids:
                        self.assertEqual(r, ("error", (403, "forbidden")))

    def test_scope_changes_between_calls_are_seen_at_once(self):
        with db.escritura(self.database) as conn:
            conn.execute("DELETE FROM maestra_base_acceso WHERE base_id = ? AND user_id = ?",
                         (self.base_a, self.u["olga"]))
            conn.execute("UPDATE inventory_terrain SET base_id = ? WHERE id = ?", (self.base_b, self.t["a2"]))
            conn.execute("UPDATE maestra_base SET archived_at = ? WHERE id = ?", (iso(0), self.base_b))
        for login in ("olga", "omar", "ana"):
            with self.subTest(cuenta=login):
                self.assert_equivalente(self.entradas()["todas"], self.s[login])

    def test_batches_larger_than_one_chunk_split_without_changing_anything(self):
        with patch.object(repo, "LOTE_RESUMENES", 2), patch.object(auth, "LOTE_LECTURA", 3):
            for login in ("ana", "olga", "omar"):
                for nombre, ids in self.entradas().items():
                    with self.subTest(cuenta=login, entrada=nombre):
                        self.assert_equivalente(ids, self.s[login])

    # -- explicit projections (not only "same as before") ----------------------------

    def test_projections_counts_order_and_privacy(self):
        a1 = self.t["a1"]
        with db.session(self.database) as conn:
            olga = self.nuevo(conn, [a1, self.t["a2"]], self.s["olga"])["resultados"]
            ana = self.nuevo(conn, [a1], self.s["ana"])["resultados"][a1]
        fila = olga[a1]
        self.assertEqual(fila["pdf_total"], 7)                    # the two retired ones do not count
        self.assertEqual(len(fila["pdf_recientes"]), 5)
        self.assertFalse(any(r["retirado"] for r in fila["pdf_recientes"]))
        versiones = [r["ultima_version"] for r in fila["pdf_recientes"]]
        # Newest first: 6 disponible, 5 cancelado, 4 fallido, then the 2/3 tie by id.
        self.assertEqual([v["estado"] for v in versiones[:3]], ["disponible", "cancelado", "fallido"])
        empate = {v["estado"] for v in versiones[3:5]}
        self.assertEqual(empate, {"subiendo", "expirado"})
        ajena_viva = next(v for v in versiones if v["estado"] == "subiendo")
        self.assertEqual(ajena_viva, {"estado": "subiendo", "propia": False})   # ana's, live lease
        self.assertEqual(next(v for v in versiones if v["estado"] == "expirado"),
                         {"estado": "expirado", "propia": False})               # omar's, overdue
        self.assertEqual(fila["kmz"]["ultima_version"]["nombre_original"], "Contorno ficticio.kmz")
        reemplazo = olga[self.t["a2"]]["kmz"]
        self.assertEqual(reemplazo["ultima_version"], {"estado": "subiendo", "propia": False})
        self.assertNotIn("Secreto ficticio", repr(olga))
        for texto in ("temporal/", "final/", "clave", "sha256"):
            self.assertNotIn(texto, repr(olga) + repr(ana))
        # The administrator sees its own live-lease upload as its own.
        propia = [r["ultima_version"] for r in ana["pdf_recientes"] if r["ultima_version"].get("propia")]
        self.assertEqual([(v["estado"], v["propia"]) for v in propia], [("subiendo", True)])

    def test_operator_scope_hides_other_bases_archived_bases_and_unassigned(self):
        with db.session(self.database) as conn:
            r = self.nuevo(conn, list(self.t.values()), self.s["olga"])
        visibles = {self.t[n] for n in ("a1", "a2", "a3", "a_archivado")}
        self.assertEqual(set(r["resultados"]), visibles)
        self.assertEqual(r["no_disponibles"], [self.t[n] for n in ("b1", "c1", "sin_base")])
        with db.session(self.database) as conn:
            todo = self.nuevo(conn, list(self.t.values()), self.s["ana"])
        self.assertEqual(set(todo["resultados"]), set(self.t.values()))
        self.assertEqual(todo["resultados"][self.t["b1"]]["pdf_total"], 2)
        self.assertIsNone(todo["resultados"][self.t["b1"]]["pdf_recientes"][0]["ultima_version"])

    # -- statement counts ---------------------------------------------------------------

    def _terrenos_extra(self, n: int) -> list[str]:
        with db.escritura(self.database) as conn:
            ids = [self._terreno(conn, self.base_a) for _ in range(n)]
            for i, tid in enumerate(ids):
                if i % 3 == 0:
                    aid = self._archivo(conn, tid, "pdf", iso(-30))
                    self._version(conn, aid, tid, 1, "disponible")
                if i % 4 == 0:
                    aid = self._archivo(conn, tid, "kmz", iso(-30))
                    self._version(conn, aid, tid, 1, "subiendo", por="omar")
        return ids

    def contar(self, fn, ids, sesion) -> int:
        with db.session(self.database) as conn:
            contador = Contador(conn)
            fn(contador, ids, sesion)
        return contador.sentencias

    def test_statement_count_is_bounded_by_batches_not_by_terrains(self):
        ids = self._terrenos_extra(200)
        cuentas: dict[str, dict[int, int]] = {}
        for login in ("ana", "olga"):
            for n in (1, 50, 100, 200):
                pagina = ids[:n]
                nuevo = self.contar(self.nuevo, pagina, self.s[login])
                anterior = self.contar(self.anterior, pagina, self.s[login])
                cuentas.setdefault(f"{login}_nuevo", {})[n] = nuevo
                cuentas.setdefault(f"{login}_anterior", {})[n] = anterior
        for login in ("ana", "olga"):
            with self.subTest(cuenta=login):
                nuevo = cuentas[f"{login}_nuevo"]
                self.assertEqual(len(set(nuevo.values())), 1, nuevo)        # the same for 1..200
                self.assertLessEqual(nuevo[200], 7, nuevo)
                self.assertGreaterEqual(cuentas[f"{login}_anterior"][200], 200 * 7)
        self.assertEqual(self.contar(self.nuevo, [], self.s["olga"]), 0)


class ResumenesLoteSQLite(ResumenesLote, unittest.TestCase):
    def prepare_database(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "resumenes.db"
        db.connect(self.database).close()


@unittest.skipUnless(URL, "No Postgres test connection configured")
class ResumenesLotePostgres(ResumenesLote, unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import psycopg
        from psycopg.conninfo import make_conninfo

        cls.schema = "test_ara_resumenes_" + uuid.uuid4().hex
        with psycopg.connect(URL) as conn:
            conn.execute(f'CREATE SCHEMA "{cls.schema}"')
        cls.environment = patch.dict(os.environ, {"ARA_MAP_DATABASE_URL": make_conninfo(
            URL, options=f"-c search_path={cls.schema}")})
        cls.environment.start()
        with postgres.session() as conn:
            conn.raw.execute(postgres.schema_sql(), prepare=False)
            postgres.migrate(conn)

    @classmethod
    def tearDownClass(cls) -> None:
        import psycopg

        cls.environment.stop()
        with psycopg.connect(URL) as conn:
            conn.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')

    def prepare_database(self) -> None:
        self.database = None
        with postgres.session() as conn:
            rows = conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
                " AND tablename <> 'workspace_metadata'").fetchall()
            names = [row["tablename"] for row in rows]
            if names:
                conn.raw.execute("TRUNCATE " + ", ".join(f'"{name}"' for name in names)
                                 + " RESTART IDENTITY CASCADE")


if __name__ == "__main__":
    unittest.main()
