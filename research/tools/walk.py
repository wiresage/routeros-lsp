"""Read-only walk of the RouterOS command tree through /console/inspect.

Writes tree.json: { "a,b,c": [[name, node-type], ...], ... } for every dir/path/cmd node.
Only `request=child` is used (no syntax/completion pass yet). Nothing is changed on the device.
"""
import json, sys, time
sys.argv = ["probe.py", "suite1_lexical.py", sys.argv[1] if len(sys.argv) > 1 else "RouterA"]
exec(open("probe.py", encoding="utf-8").read().replace("\nmain()\n", "\n"))

def children(path):
    for attempt in range(3):
        try:
            out = run(":put [:serialize to=json [/console/inspect as-value request=child path=" + ",".join(path) + "]]", timeout=60)
            data = json.loads(out)
            data = [] if data is None else ([data] if isinstance(data, dict) else data)
            return [(x["name"], x["node-type"]) for x in data if x.get("type") == "child"]
        except Exception as e:
            time.sleep(1 + attempt)
            global C, SFTP
            try:
                C = connect()
            except Exception:
                pass
    return None

tree, queue, seen, calls, failed = {}, [()], set(), 0, []
t0 = time.time()
while queue:
    path = queue.pop(0)
    if path in seen or len(path) > 9:
        continue
    seen.add(path)
    kids = children(path)
    calls += 1
    if kids is None:
        failed.append(",".join(path)); continue
    tree[",".join(path)] = kids
    for name, ntype in kids:
        if name == "root" and not path:
            continue
        if ntype in ("dir", "path", "cmd"):
            queue.append(path + (name,))
    if calls % 1000 == 0:
        el = time.time() - t0
        print("calls=%d queue=%d nodes=%d elapsed=%.0fs (%.0f ms/call)" % (calls, len(queue), len(tree), el, el / calls * 1000), flush=True)
        json.dump(tree, open("tree.json", "w", encoding="utf-8"))
json.dump(tree, open("tree.json", "w", encoding="utf-8"))
print("DONE calls=%d nodes=%d failed=%d elapsed=%.0fs" % (calls, len(tree), len(failed), time.time() - t0), flush=True)
