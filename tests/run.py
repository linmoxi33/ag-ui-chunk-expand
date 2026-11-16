#!/usr/bin/env python3
"""10 cases: 4 unit, 6 behavioural subprocess."""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import agui_chunk_expand as m  # noqa: E402
CLI = os.path.join(ROOT, "agui_chunk_expand.py")
CASES = []

def case(fn):
    CASES.append(fn); return fn

def sse(*events):
    return "".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()

def run(*args):
    p = subprocess.run([sys.executable, CLI, *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

@case
def text_chunk_expands_to_three():
    ev = [{"type":"TEXT_MESSAGE_CHUNK","messageId":"m","role":"assistant","delta":"x"}]
    out, c = m.expand(ev)
    assert [e["type"] for e in out] == ["TEXT_MESSAGE_START","TEXT_MESSAGE_CONTENT","TEXT_MESSAGE_END"]
    assert not c

@case
def tool_chunk_expands_with_args():
    ev = [{"type":"TOOL_CALL_CHUNK","toolCallId":"c","toolCallName":"t","args":"{}"}]
    out, c = m.expand(ev)
    assert [e["type"] for e in out] == ["TOOL_CALL_START","TOOL_CALL_ARGS","TOOL_CALL_END"]

@case
def role_conflict_reported():
    ev = [{"type":"TEXT_MESSAGE_CHUNK","messageId":"m","role":"assistant","delta":"a"},
          {"type":"TEXT_MESSAGE_CHUNK","messageId":"m","role":"user","delta":"b"}]
    _, c = m.expand(ev)
    assert [x["code"] for x in c] == ["C011"], c

@case
def missing_first_id_reported():
    ev = [{"type":"TEXT_MESSAGE_CHUNK","delta":"x"}]
    _, c = m.expand(ev)
    assert c and c[0]["code"] == "C010"

@case
def cli_compact_exit_zero():
    rc, out, _ = run("examples/in/compact.sse")
    assert rc == 0 and "6 in, 10 out" in out, (rc, out)

@case
def cli_conflict_exit_one():
    rc, out, _ = run("examples/in/conflict.sse")
    assert rc == 1 and "C011" in out, (rc, out)

@case
def cli_json_parses():
    rc, out, _ = run("examples/in/compact.sse", "--json")
    r = json.loads(out)
    assert rc == 0 and r["ok"] and r["input_events"] == 6 and r["expanded_events"] == 10, r

@case
def cli_provenance_flag():
    rc, out, _ = run("examples/in/compact.sse", "--json", "--keep-provenance")
    r = json.loads(out)
    assert rc == 0 and sum("_from" in e for e in r["events"]) == 8, r

@case
def cli_missing_file_exit_two():
    rc, _, err = run("/nope/x.sse")
    assert rc == 2 and "ag-ui-chunk-expand" in err

@case
def cli_bad_json_exit_two():
    with open("/tmp/_ce_bad.sse","w") as fh: fh.write("data: {oops}\n\n")
    rc, _, _ = run("/tmp/_ce_bad.sse")
    assert rc == 2

def main():
    failed = 0
    for fn in CASES:
        try:
            fn(); print("PASS", fn.__name__)
        except AssertionError as exc:
            failed += 1; print("FAIL", fn.__name__, exc)
    print(f"\n{len(CASES)-failed} passed, {failed} failed ({len(CASES)} cases)")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
