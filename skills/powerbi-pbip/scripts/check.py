"""Post-generation invariants. Aborts if a PBIP has the silent failure modes."""
import glob
import json
import pathlib
import sys


def check(project: str) -> list[str]:
    p = pathlib.Path(project)
    fail = []
    if not p.with_suffix(".pbip").exists():
        fail.append(f"{project}.pbip missing")

    rep = p.with_name(p.name + ".Report")
    sem = p.with_name(p.name + ".SemanticModel")

    pages = json.load(open(rep / "definition/pages/pages.json", encoding="utf-8"))
    if not pages.get("pageOrder") or not pages.get("activePageName"):
        fail.append(f"{project}: pages.json has no pageOrder/activePageName")

    tmdl = next(sem.glob("definition/tables/*.tmdl")).read_text(encoding="utf-8")
    if "Table.TransformColumnTypes" not in tmdl:
        fail.append(f"{project}: partition does not pin column types")

    visuals = glob.glob(str(rep / "definition/pages/*/visuals/*/visual.json"))
    if not visuals:
        fail.append(f"{project}: no visuals generated")
    for vf in visuals:
        visual = json.load(open(vf, encoding="utf-8"))
        qs = visual["visual"]["query"]["queryState"]
        if not qs:
            fail.append(f"{vf}: empty queryState")
        if "Legend" in qs:
            fail.append(f"{vf}: role 'Legend' is silently ignored by Desktop")
    return fail, len(visuals)


def main() -> None:
    projects = sys.argv[1:] or ["build/finance/FinanceDemo", "build/sales/SalesDemo"]
    fail = []
    for proj in projects:
        errs, n = check(proj)
        fail += errs
        print(f"{proj}: {n} visuals checked")
    if fail:
        print("\n".join(fail))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
