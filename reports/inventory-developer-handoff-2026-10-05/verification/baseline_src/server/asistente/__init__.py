"""The import assistant: turn differently organized Excel/CSV tables into terrains.

Stages, each in its own module and each ignorant of the next:

    rejilla   parse the file's structure (sheets, rows, cells) -- no field names
    perfil    describe each column of a chosen table (labels, types, samples)
    detectar  suggest a table, header, field assignments and questions
    plan      the explicit, versioned ImportPlan and the records it produces
    ia        optional automatic assistance for what detection could not settle
    servicio  the orchestration the HTTP endpoints call

Nothing here writes business data: the result is an ordinary ImportResult that
goes through the existing preview/confirmation path.
"""
