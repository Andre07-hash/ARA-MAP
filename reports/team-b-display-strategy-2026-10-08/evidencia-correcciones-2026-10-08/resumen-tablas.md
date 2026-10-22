| Case | Renderer | Cold: longest task, new (old) | Cold: synchronous call, worst | Views: longest task, new (old) | Views: tasks ≥ 50 ms, new (old) | Direct redraw: call, worst | Input→paint worst | Selection longest task | Cancellation longest task, new (old) | Cancellation / teardown clean |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B-2 fixture, 12 rows | b2 | **0** (0) | 10 | **0** (0) | 0 (0) | 1 | 32 | 0 | **137** (143) | yes / yes |
| B-2 fixture, 12 rows | E1 (lineTo) | **0** (0) | 11 | **0** (0) | 0 (0) | 1 | 32 | 0 | **119** (144) | yes / yes |
| B-2 fixture, 12 rows | E1p (Path2D) | **0** (n/a) | 14 | **0** (n/a) | 0 (n/a) | 1 | 24 | 0 | **140** (n/a) | yes / yes |
| B-2 fixture, 12 rows | E2 | **0** (0) | 12 | **0** (0) | 0 (0) | 2 | 40 | 0 | **66** (73) | yes / yes |
| B-2 fixture, 12 rows | E3 | **0** (0) | 10 | **0** (0) | 0 (0) | 3 | 24 | 0 | **0** (0) | yes / yes |
| B-2 fixture, 12 rows | E4 | **0** (0) | 12 | **0** (0) | 0 (0) | 1 | 24 | 0 | **0** (0) | yes / yes |
| 500 XY points | b2 | **0** (0) | 28 | **0** (0) | 0 (0) | 3 | 24 | 0 | **140** (133) | yes / yes |
| 500 XY points | E1 (lineTo) | **0** (0) | 26 | **0** (0) | 0 (0) | 3 | 32 | 0 | **98** (109) | yes / yes |
| 500 XY points | E1p (Path2D) | **0** (n/a) | 31 | **0** (n/a) | 0 (n/a) | 3 | 32 | 0 | **98** (n/a) | yes / yes |
| 500 XY points | E2 | **0** (0) | 30 | **0** (0) | 0 (0) | 3 | 40 | 0 | **0** (0) | yes / yes |
| 500 XY points | E3 | **0** (0) | 35 | **0** (0) | 0 (0) | 4 | 32 | 0 | **0** (0) | yes / yes |
| 500 XY points | E4 | **52** (0) | 36 | **0** (0) | 0 (0) | 3 | 40 | 0 | **0** (0) | yes / yes |
| One ring, 100,000 positions | b2 | **227** (0) | 59 | **74** (53) | 5 (4) | 74 | 32 | 0 | **106** (106) | yes / yes |
| One ring, 100,000 positions | E1 (lineTo) | **204** (0) | 50 | **97** (65) | 9 (5) | 98 | 24 | 0 | **130** (105) | yes / yes |
| One ring, 100,000 positions | E1p (Path2D) | **220** (n/a) | 60 | **99** (n/a) | 7 (n/a) | 100 | 32 | 0 | **110** (n/a) | yes / yes |
| One ring, 100,000 positions | E2 | **317** (300) | 33 | **228** (357) | 42 (39) | 7 | 152 | 138 | **226** (159) | yes / yes |
| One ring, 100,000 positions | E3 | **135** (139) | 9 | **214** (278) | 42 (39) | 7 | 200 | 180 | **142** (157) | yes / yes |
| One ring, 100,000 positions | E4 | **0** (0) | 12 | **0** (0) | 0 (0) | 1 | 24 | 0 | **0** (0) | yes / yes |
| 20,000 scattered parts | b2 | **237** (0) | 108 | **90** (0) | 3 (0) | 91 | 24 | 0 | **131** (161) | yes / yes |
| 20,000 scattered parts | E1 (lineTo) | **227** (0) | 125 | **77** (51) | 4 (1) | 78 | 32 | 0 | **158** (145) | yes / yes |
| 20,000 scattered parts | E1p (Path2D) | **240** (n/a) | 118 | **80** (n/a) | 6 (n/a) | 80 | 56 | 0 | **152** (n/a) | yes / yes |
| 20,000 scattered parts | E2 | **0** (0) | 43 | **0** (0) | 0 (0) | 1 | 32 | 0 | **0** (0) | yes / yes |
| 20,000 scattered parts | E3 | **0** (0) | 10 | **81** (0) | 2 (0) | 1 | 32 | 0 | **0** (0) | yes / yes |
| 20,000 scattered parts | E4 | **0** (0) | 10 | **0** (0) | 0 (0) | 2 | 32 | 0 | **0** (0) | yes / yes |
| One large part + 19,999 small | b2 | **2,351** (2,433) | 134 | **1,186** (1,177) | 40 (28) | 582 | 976 | 957 | **945** (939) | yes / yes |
| One large part + 19,999 small | E1 (lineTo) | **290** (185) | 117 | **138** (123) | 36 (21) | 111 | 168 | 135 | **185** (110) | yes / yes |
| One large part + 19,999 small | E1p (Path2D) | **410** (n/a) | 142 | **115** (n/a) | 25 (n/a) | 116 | 136 | 109 | **128** (n/a) | yes / yes |
| One large part + 19,999 small | E2 | **392** (385) | 40 | **234** (230) | 29 (24) | 6 | 232 | 221 | **214** (196) | yes / yes |
| One large part + 19,999 small | E3 | **219** (193) | 14 | **201** (213) | 29 (24) | 5 | 208 | 195 | **212** (259) | yes / yes |
| One large part + 19,999 small | E4 | **0** (0) | 10 | **0** (0) | 0 (0) | 2 | 32 | 0 | **0** (0) | yes / yes |
| Dense: large + 19,999, all visible | b2 | **4,469** (4,423) | 175 | **2,490** (2,300) | 46 (27) | 970 | 1,536 | 1,523 | **1,469** (1,523) | yes / yes |
| Dense: large + 19,999, all visible | E1 (lineTo) | **297** (334) | 117 | **278** (181) | 37 (26) | 98 | 168 | 154 | **133** (140) | yes / yes |
| Dense: large + 19,999, all visible | E1p (Path2D) | **378** (n/a) | 140 | **179** (n/a) | 37 (n/a) | 96 | 136 | 126 | **138** (n/a) | yes / yes |
| Dense: large + 19,999, all visible | E2 | **344** (366) | 52 | **176** (212) | 28 (23) | 6 | 176 | 165 | **168** (201) | yes / yes |
| Dense: large + 19,999, all visible | E3 | **185** (236) | 9 | **198** (266) | 30 (25) | 4 | 176 | 165 | **190** (199) | yes / yes |
| Dense: large + 19,999, all visible | E4 | **0** (0) | 10 | **0** (0) | 0 (0) | 3 | 24 | 0 | **0** (0) | yes / yes |

Selection correct everywhere: True

| Renderer | Visits: long tasks / longest, new (old) | Main cache peak | Worker bytes (entries) after visits | Worker counted max | Reset: cache / worker confirmed |
|---|---|---|---|---|---|
| b2 | 19 / 193 ms (11 / 101) | 0 B | — (None) | — | None / — → — B |
| E1 (lineTo) | 18 / 140 ms (22 / 98) | 0 B | — (None) | — | 0 / — → — B |
| E1p (Path2D) | 11 / 172 ms (n/a / n/a) | 0 B | — (None) | — | 0 / — → — B |
| E2 | 53 / 107 ms (58 / 107) | 32,641,632 B | — (None) | — | 0 / — → — B |
| E3 | 4 / 81 ms (12 / 162) | 32,641,632 B | — (None) | — | 0 / — → — B |
| E4 | 0 / 0 ms (0 / 0) | 32,641,632 B | 32,641,632 (34) | 32,641,632 | 0 / True → 0 B |

Controls:
{'fase': 'frio', 'tareaMaxMs': 171, 'filtroAnterior': 0, 'llamadaMs': 162.1, 'detectada': True, 'fallaCriterio50': True}
{'fase': 'pan-directo', 'tareaMaxMs': 155, 'filtroAnterior': 0, 'llamadaMs': 150.4, 'detectada': True, 'fallaCriterio50': True}
{'fase': 'pan-directo', 'tareaMaxMs': 155, 'filtroAnterior': 0, 'llamadaMs': 150.3, 'detectada': True, 'fallaCriterio50': True}
{'fase': 'zoom-directo', 'tareaMaxMs': 156, 'filtroAnterior': 0, 'llamadaMs': 150.9, 'detectada': True, 'fallaCriterio50': True}
{'fase': 'zoom-directo', 'tareaMaxMs': 158, 'filtroAnterior': 0, 'llamadaMs': 153, 'detectada': True, 'fallaCriterio50': True}
{'fase': 'cancelacion', 'tareaMaxMs': 156, 'filtroAnterior': 121, 'llamadaMs': 151.8, 'detectada': True, 'fallaCriterio50': True}
{'fase': 'tarea-anterior-al-marcador', 'tareaMaxMs': 0, 'filtroAnterior': 0, 'llamadaMs': None, 'detectada': True, 'fallaCriterio50': False}

Paint (overview/detail) vs b2:
fixture e1 1440x768 identico True iou 1 detalle True 1
fixture e1p 1440x768 identico True iou 1 detalle True 1
fixture e2 1440x768 identico False iou 0.9973 detalle False 0.9973
fixture e3 1440x768 identico False iou 0.9973 detalle False 0.9973
fixture e4 1440x768 identico False iou 0.9973 detalle False 0.9973
xy e1 1440x768 identico True iou 1 detalle True 1
xy e1p 1440x768 identico True iou 1 detalle True 1
xy e2 1440x768 identico True iou 1 detalle True 1
xy e3 1440x768 identico True iou 1 detalle True 1
xy e4 1440x768 identico True iou 1 detalle True 1
circulo-100k e1 1440x768 identico True iou 1 detalle True 1
circulo-100k e1p 1440x768 identico True iou 1 detalle True 1
circulo-100k e2 1440x768 identico False iou 0.9974 detalle False 0.9975
circulo-100k e3 1440x768 identico False iou 0.9974 detalle False 0.9975
circulo-100k e4 1440x768 identico False iou 0.9975 detalle False 0.9975
multiparte-20000 e1 1440x768 identico True iou 1 detalle True 1
multiparte-20000 e1p 1440x768 identico True iou 1 detalle True 1
multiparte-20000 e2 1440x768 identico False iou 0.9539 detalle False 0.9693
multiparte-20000 e3 1440x768 identico False iou 0.9539 detalle False 0.9693
multiparte-20000 e4 1440x768 identico False iou 0.9539 detalle False 0.9693
grande-mas-19999 e1 1440x768 identico True iou 1 detalle True 1
grande-mas-19999 e1p 1440x768 identico False iou 0.7343 detalle False 0.726
grande-mas-19999 e2 1440x768 identico False iou 0.5 detalle False 0.4992
grande-mas-19999 e3 1440x768 identico False iou 0.5 detalle False 0.4992
grande-mas-19999 e4 1440x768 identico False iou 0.5 detalle False 0.4992
denso-grande-mas-19999 e1 1440x768 identico True iou 1 detalle True 1
denso-grande-mas-19999 e1p 1440x768 identico True iou 1 detalle True 1
denso-grande-mas-19999 e2 1440x768 identico False iou 0.9941 detalle False 0.9936
denso-grande-mas-19999 e3 1440x768 identico False iou 0.9941 detalle False 0.9936
denso-grande-mas-19999 e4 1440x768 identico False iou 0.9941 detalle False 0.9936
