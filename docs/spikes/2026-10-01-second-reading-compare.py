import json, collections, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
def per(ms, bad): return collections.Counter(p for p, s, st in ms if (st == "broken") == bad)
ga, gb, ba, bb = per(a["moves"], False), per(b["moves"], False), per(a["moves"], True), per(b["moves"], True)
print("good", sum(ga.values()), "->", sum(gb.values()), "| broken", sum(ba.values()), "->", sum(bb.values()))
print("diagram verdicts", a["verdicts"], "->", b["verdicts"])
print("pages losing good moves:", [(p, ga[p], gb[p]) for p in sorted(set(ga) | set(gb)) if gb[p] < ga[p]])
gold = lambda ms: [(p, s, st) for p, s, st in ms if 14 <= p <= 26]
ok_a = [(p, s) for p, s, st in gold(a["moves"]) if st != "broken"]
ok_b = collections.Counter((p, s) for p, s, st in gold(b["moves"]) if st != "broken")
missing = [x for x in ok_a if not ok_b[x] or ok_b.subtract([x])]
print("verified pages 14-26: good moves no longer good:", len([x for x in ok_a if (p := x) and False]) or None)
print("page 27:", (ga[27], ba[27]), "->", (gb[27], bb[27]))
print([(p, (ga[p], ba[p]), (gb[p], bb[p])) for p in range(14, 31)])
