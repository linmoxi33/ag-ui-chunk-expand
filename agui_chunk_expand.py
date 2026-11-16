#!/usr/bin/env python3
"""Expand recorded AG-UI compact chunk events into canonical START/CONTENT/END events.

Spec: docs/spec/1.0/events/text-messages.mdx — a consumer MUST expand chunks,
including first-chunk requirements and the conflicting-repeat rule. This tool
does that expansion offline, and reports conflicts instead of silently picking
a winner (see upstream issue #3264 for the class of bug: chunk arguments being
discarded on message replacement).

Exit: 0 expanded cleanly, 1 conflicts, 2 usage/input.
"""
from __future__ import annotations
import argparse, json, sys

TEXT = "TEXT"
TOOL = "TOOL"


def parse_stream(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8", errors="replace")
    events, data = [], []
    for line in text.splitlines():
        if line == "":
            if data:
                events.append(json.loads("\n".join(data)))
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        events.append(json.loads("\n".join(data)))
    return events


def expand(events: list[dict]) -> tuple[list[dict], list[dict]]:
    out: list[dict] = []
    conflicts: list[dict] = []
    open_text: dict | None = None      # {"messageId": str, "role": str|None}
    open_tool: dict | None = None      # {"toolCallId": str, "name": str|None}

    def close_text(idx: int) -> None:
        nonlocal open_text
        if open_text is not None:
            out.append({"type": "TEXT_MESSAGE_END", "messageId": open_text["messageId"],
                        "_from": idx})
            open_text = None

    def close_tool(idx: int) -> None:
        nonlocal open_tool
        if open_tool is not None:
            out.append({"type": "TOOL_CALL_END", "toolCallId": open_tool["toolCallId"],
                        "_from": idx})
            open_tool = None

    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            conflicts.append({"code": "C000", "index": i, "message": "event is not an object"})
            continue
        t = ev.get("type")
        if t in ("TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
                 "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END"):
            close_text(i); close_tool(i)
            out.append(ev)
            continue
        if t == "RUN_FINISHED" or t == "RUN_ERROR":
            close_text(i); close_tool(i)
            out.append(ev)
            continue
        if t == "TEXT_MESSAGE_CHUNK":
            mid = ev.get("messageId")
            role = ev.get("role")
            if open_text is not None and mid is not None and open_text["messageId"] != mid:
                close_text(i)
            if open_text is None:
                if not isinstance(mid, str):
                    conflicts.append({"code": "C010", "index": i,
                                      "message": "first TEXT_MESSAGE_CHUNK must carry messageId"})
                    continue
                open_text = {"messageId": mid, "role": role}
                out.append({"type": "TEXT_MESSAGE_START", "messageId": mid, "role": role,
                            "_from": i})
            else:
                if role is not None and open_text["role"] is not None and role != open_text["role"]:
                    conflicts.append({"code": "C011", "index": i,
                                      "message": f"conflicting role {open_text['role']!r} -> {role!r}",
                                      "messageId": mid})
                if role is not None and open_text["role"] is None:
                    open_text["role"] = role
                    out.append({"type": "TEXT_MESSAGE_START", "messageId": open_text["messageId"],
                                "role": role, "_from": i})
            delta = ev.get("delta")
            if delta is not None:
                out.append({"type": "TEXT_MESSAGE_CONTENT", "messageId": open_text["messageId"],
                            "delta": delta, "_from": i})
            continue
        if t == "TOOL_CALL_CHUNK":
            tid = ev.get("toolCallId")
            name = ev.get("toolCallName")
            if open_tool is not None and tid is not None and open_tool["toolCallId"] != tid:
                close_tool(i)
            if open_tool is None:
                if not isinstance(tid, str):
                    conflicts.append({"code": "C020", "index": i,
                                      "message": "first TOOL_CALL_CHUNK must carry toolCallId"})
                    continue
                open_tool = {"toolCallId": tid, "name": name}
                out.append({"type": "TOOL_CALL_START", "toolCallId": tid, "toolCallName": name,
                            "_from": i})
            else:
                if name is not None and open_tool["name"] is not None and name != open_tool["name"]:
                    conflicts.append({"code": "C021", "index": i,
                                      "message": f"conflicting toolCallName {open_tool['name']!r} -> {name!r}",
                                      "toolCallId": tid})
                if name is not None and open_tool["name"] is None:
                    open_tool["name"] = name
                    out.append({"type": "TOOL_CALL_START", "toolCallId": open_tool["toolCallId"],
                                "toolCallName": name, "_from": i})
            if ev.get("args") is not None:
                out.append({"type": "TOOL_CALL_ARGS", "toolCallId": open_tool["toolCallId"],
                            "delta": ev["args"], "_from": i})
            continue
        out.append(ev)
    close_text(len(events)); close_tool(len(events))
    return out, conflicts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ag-ui-chunk-expand")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--keep-provenance", action="store_true",
                    help="keep _from event indices in expanded output")
    args = ap.parse_args(argv)
    try:
        events = parse_stream(open(args.file, "rb").read())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ag-ui-chunk-expand: {exc}", file=sys.stderr)
        return 2
    out, conflicts = expand(events)
    if not args.keep_provenance:
        for ev in out:
            ev.pop("_from", None)
    report = {"ok": not conflicts, "input_events": len(events), "expanded_events": len(out),
              "conflicts": conflicts, "events": out}
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for c in conflicts:
            print(f"CONFLICT {c['code']} @event {c['index']}: {c['message']}")
        for ev in out:
            print(ev["type"], json.dumps({k: v for k, v in ev.items() if k != "type"}, ensure_ascii=False))
        print(f"{len(events)} in, {len(out)} out, {len(conflicts)} conflict(s)")
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
