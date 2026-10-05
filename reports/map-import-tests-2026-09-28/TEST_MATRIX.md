# MapTest file matrix

All terrain information is fictional. PASS includes the explicitly stated safe limitations for UTM and USD headers. MISMATCH is a content comparison, not an automatic claim of a new defect. See DEVELOPER_REPORT.md for priorities and distinctions.

| File | Scenario | Guided result | Question rounds | Saved rows | Expected rows | Interpretation |
|---|---|---|---|---|---|---|
| [MapTest1.xlsx](files/MapTest1.xlsx) | Excel standard control | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest2.csv](files/MapTest2.csv) | Reordered columns | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest3.csv](files/MapTest3.csv) | Semicolon and decimal comma | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest4.xlsx](files/MapTest4.xlsx) | Title, merged banner and blank rows | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest5.xlsx](files/MapTest5.xlsx) | Instructions sheet before terrain sheet | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest6.csv](files/MapTest6.csv) | Repeated header inside table | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest7.csv](files/MapTest7.csv) | Summary total row | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest8.xlsx](files/MapTest8.xlsx) | Repeated price headers: total and unit | MISMATCH | 1 | 4 | 4 | Manual column mapping recovers all values; guided choice leaves unit price in extra data. |
| [MapTest9.csv](files/MapTest9.csv) | English headers | PASS | 3 | 4 | 4 | Matches the intended records after the listed focused questions. |
| [MapTest10.csv](files/MapTest10.csv) | Unknown headers require mapping | PASS | 5 | 4 | 4 | Matches the intended records after the listed focused questions. |
| [MapTest11.xlsx](files/MapTest11.xlsx) | Two header rows with units | PASS | 2 | 4 | 4 | Matches the intended records after the listed focused questions. |
| [MapTest12.xlsx](files/MapTest12.xlsx) | Transposed property cards | UNRESOLVED | 5 |  | 4 | Transposed layout unsupported; no usable preview after guided answers. |
| [MapTest13.xlsx](files/MapTest13.xlsx) | Two side-by-side terrain tables | MISMATCH | 4 | 2 | 4 | Only the left table becomes two terrain records; the right table remains extra columns. |
| [MapTest14.xlsx](files/MapTest14.xlsx) | Two valid worksheets: choose one | PASS | 1 | 2 | 2 | Matches the intended records after the listed focused questions. |
| [MapTest15.csv](files/MapTest15.csv) | Coordinates together in one cell | MISMATCH | 0 | 4 | 4 | Combined coordinate cell remains extra data; 4/4 terrains unlocated. |
| [MapTest16.csv](files/MapTest16.csv) | Degrees minutes seconds coordinates | MISMATCH | 0 | 4 | 4 | DMS strings are not parsed as coordinates; 4/4 terrains unlocated. |
| [MapTest17.csv](files/MapTest17.csv) | Projected UTM coordinates | PASS | 0 | 4 | 4 | Safe limitation: UTM remains extra data; no fabricated lat/lon. |
| [MapTest18.csv](files/MapTest18.csv) | Mixed decimal conventions by column | MISMATCH | 1 | 4 | 4 | One global decimal convention cannot preserve both column formats; price fields become null with warnings. |
| [MapTest19.csv](files/MapTest19.csv) | USD stated in header | PASS | 0 | 4 | 4 | Safe limitation: explicit USD prices stay extra data, not MXN. |
| [MapTest20.xlsx](files/MapTest20.xlsx) | USD stated only in Excel number format | MISMATCH | 0 | 4 | 4 | F1: Excel USD formatting lost; all four amounts committed as MXN. |
| [MapTest21.xlsx](files/MapTest21.xlsx) | Native Excel percentage values | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest22.csv](files/MapTest22.csv) | Legitimate terrain name begins with Total | MISMATCH | 0 | 3 | 4 | F2: Total FICTICIO Encino dropped; only three terrains saved. |
| [MapTest23.csv](files/MapTest23.csv) | Footnote below data | MISMATCH | 0 | 5 | 4 | F5: note footer becomes a fifth terrain. API exclusion works; no browser row-exclusion control. |
| [MapTest24.xlsx](files/MapTest24.xlsx) | Leading blank rows and columns | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest25.csv](files/MapTest25.csv) | Decimal comma coordinates with quoted comma CSV | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest26.csv](files/MapTest26.csv) | Quotes, comma and multiline extra text | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest27.csv](files/MapTest27.csv) | UTF-16 Excel CSV export | REJECTED | 0 |  | 4 | Known encoding limitation: clear instruction to re-export as UTF-8. |
| [MapTest28.csv](files/MapTest28.csv) | Windows-1252 CSV export | REJECTED | 0 |  | 4 | Known encoding limitation: clear instruction to re-export as UTF-8. |
| [MapTest29.csv](files/MapTest29.csv) | Tab-delimited file with .csv extension | MISMATCH | 1 | 4 | 4 | F3: tabs collapse into a single name field; wrong terrain names and missing values. |
| [MapTest30.csv](files/MapTest30.csv) | Malformed CSV quoting | REJECTED | 0 |  | 4 | Expected rejection: unterminated quoted field. |
| [MapTest31.csv](files/MapTest31.csv) | Empty CSV | REJECTED | 0 |  | 4 | Expected rejection: empty upload. |
| [MapTest32.csv](files/MapTest32.csv) | Blank price versus real zero | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest33.xlsx](files/MapTest33.xlsx) | Price formulas with cached results | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
| [MapTest34.csv](files/MapTest34.csv) | Table without a header row | MISMATCH | 5 | 3 | 4 | No headerless mode; first terrain becomes header and is omitted. |
| [MapTest35.xlsx](files/MapTest35.xlsx) | Header after 55 nonblank introduction lines | UNRESOLVED | 5 |  | 4 | F4: header at row 56 absent from correction menu. Direct API correction succeeds. |
| [MapTest36.csv](files/MapTest36.csv) | UTF-8 BOM and explicit separator directive | PASS | 0 | 4 | 4 | Matches the intended records without questions. |
