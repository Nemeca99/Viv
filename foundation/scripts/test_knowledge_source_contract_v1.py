"""Focused read-only proof for the three-source knowledge contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIV = ROOT.parent
for path in (ROOT, VIV):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lib.knowledge_source_contract import (  # noqa: E402
    GroundedFact,
    assess_three_way,
    build_fact_packet,
    describe_file,
    sample_text_files,
)
from lib.aios_adapter_knowledge import query_manual_packet, query_packet  # noqa: E402
from lib.knowledge_claim_alignment import align_claims  # noqa: E402
from lib.knowledge_external_adapters import (  # noqa: E402
    compose_multi_source_packet,
    runtime_authority_fact,
    wikipedia_fact_from_payload,
)
from lib.knowledge_source_contract import SourceRef  # noqa: E402
from voice_core.intent_packet import build_intent_packet, packet_to_messages  # noqa: E402


def main() -> int:
    samples = sample_text_files(r"F:\AI_Datasets", max_files=2, max_bytes_each=4096)
    if not samples:
        raise SystemExit("no_text_sample_found")
    first = samples[0]["source"]
    ref = describe_file(first["path"])
    fact = GroundedFact(
        claim="source sample is hash identified",
        value=ref.sha256,
        source=ref,
        scope="read_only_probe",
    )
    verified = build_fact_packet("source identity", [fact])
    conflict = build_fact_packet(
        "conflict probe",
        [fact, GroundedFact("source sample is hash identified", "different", ref, scope="read_only_probe")],
    )
    partial = assess_three_way([fact])
    wiki_fact = wikipedia_fact_from_payload(
        "Evolution",
        {"extract": "Evolution is change in heritable characteristics across generations."},
    )
    runtime_probe = SourceRef(
        source_id="sha256:runtime-probe",
        path="runtime_authority:probe",
        root="runtime_authority",
        kind="runtime_probe",
        bytes=1,
        modified_utc=None,
        sha256="runtime-probe",
        readable=True,
    )
    agreed = assess_three_way(
        [
            GroundedFact(
                "same claim",
                "same value",
                SourceRef(
                    source_id=fact.source.source_id,
                    path="SRC_F_AI_DATASETS_probe",
                    root="F_AI_DATASETS",
                    kind="dataset_probe",
                    bytes=fact.source.bytes,
                    modified_utc=fact.source.modified_utc,
                    sha256=fact.source.sha256,
                    readable=True,
                ),
            ),
            GroundedFact("same claim", "same value", wiki_fact.source),
            GroundedFact("same claim", "same value", runtime_probe),
        ]
    )
    runtime = runtime_authority_fact()
    composed = compose_multi_source_packet("evolution", wikipedia_title="Evolution", include_runtime=True)
    alignment = align_claims("evolution", composed.get("packet", {}).get("facts") or [])
    retrieved = query_packet("evolution", k=2)
    manual = query_manual_packet("architecture manual", k=2)
    mouth = build_intent_packet(
        query="What is evolution?",
        mode="converse",
        knowledge_query="evolution",
        memory_top=1,
    )
    multi_mouth = build_intent_packet(
        query="What is evolution?",
        mode="converse",
        knowledge_query="evolution",
        knowledge_mode="multi_source",
        wikipedia_title="Evolution",
        memory_top=1,
    )
    mouth_knowledge = mouth.get("knowledge_packet") or {}
    mouth_messages = packet_to_messages(mouth)
    mouth_wire = "\n".join(str(row.get("content") or "") for row in mouth_messages)
    multi_facts = [str(value) for value in multi_mouth.get("facts") or []]
    result = {
        "ok": (
            ref.sha256 == first["sha256"]
            and verified["state"] == "VERIFIED"
            and conflict["state"] == "CONFLICT"
            and partial["state"] == "PARTIAL"
            and agreed["state"] == "AGREED"
            and runtime.get("state") in {"VERIFIED", "UNVERIFIED", "INCONCLUSIVE"}
            and composed.get("ok")
            and composed.get("packet", {}).get("authority") == "knowledge_multi_source_v1"
            and composed.get("packet", {}).get("three_way", {}).get("state") == "PARTIAL"
            and alignment.get("state") == "INCONCLUSIVE"
            and "lib.viv_shadow_judge.semantic_compare" in alignment.get("judge_interfaces", [])
            and retrieved.get("ok")
            and retrieved.get("packet", {}).get("authority") == "knowledge_retrieval_v1"
            and manual.get("ok")
            and manual.get("state") == "VERIFIED"
            and manual.get("packet", {}).get("facts")
            and all(
                (fact.get("source") or {}).get("root") == "L_VIV_FOUNDATION"
                and (fact.get("source") or {}).get("sha256")
                for fact in manual.get("packet", {}).get("facts") or []
            )
            and mouth_knowledge.get("state") == "VERIFIED"
            and any(str(value).startswith("know=") for value in mouth.get("facts") or [])
            and all("master_s_n" not in str(value).lower() for value in mouth.get("facts") or [] if str(value).startswith("know="))
            and (multi_mouth.get("knowledge_packet") or {}).get("three_way", {}).get("state") == "PARTIAL"
            and any(value.startswith("know=") for value in multi_facts)
            and any(value.startswith("know_uncertainty=") for value in multi_facts)
            and all("runtime_authority_state" not in value for value in multi_facts)
            and "master_s_n" not in mouth_wire.lower()
            and "<telemetry" not in mouth_wire.lower()
            and all(row["source"]["path"].startswith("F:/AI_Datasets/") for row in samples)
        ),
        "sample_count": len(samples),
        "samples": [
            {"path": row["source"]["path"], "bytes": row["source"]["bytes"], "sha256": row["source"]["sha256"], "sample_chars": row["sample_chars"]}
            for row in samples
        ],
        "verified_state": verified["state"],
        "conflict_state": conflict["state"],
        "three_way_state_single_source": partial["state"],
        "three_way_state_complete_probe": agreed["state"],
        "runtime_authority_state": runtime.get("state"),
        "composed_state": composed.get("packet", {}).get("three_way", {}).get("state"),
        "composed_present_sources": composed.get("packet", {}).get("three_way", {}).get("present_sources"),
        "claim_alignment_state": alignment.get("state"),
        "claim_alignment_min_overlap": alignment.get("min_overlap"),
        "claim_alignment_judge": alignment.get("judge_interfaces"),
        "retrieval_packet_state": retrieved.get("packet", {}).get("state"),
        "retrieval_hit_count": len(retrieved.get("hits") or []),
        "manual_packet_state": manual.get("packet", {}).get("state"),
        "manual_packet_hit_count": len(manual.get("hits") or []),
        "mouth_knowledge_state": mouth_knowledge.get("state"),
        "mouth_knowledge_fact_count": sum(1 for value in mouth.get("facts") or [] if str(value).startswith("know=")),
        "ordinary_mouth_telemetry_absent": "master_s_n" not in mouth_wire.lower() and "<telemetry" not in mouth_wire.lower(),
        "multi_source_mouth_state": (multi_mouth.get("knowledge_packet") or {}).get("three_way", {}).get("state"),
    }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
