#!/usr/bin/env python3
"""Build the final six-case explicit-relationship repair plus anchors."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
SOURCE = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_training_recovery_v2_anchor_coverage_v1_3/train_256.jsonl"
ROOT = FOUNDATION / "artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4/campaigns/mouth_final_hold_repair_v1"
TARGETS = [
 ("architecture_cpu_gpu_role", "Is the GPU the thinking part of AIOS?", "No. CPU-side Viv, the AIOS authority, reasons and decides; the replaceable GPU model only renders Viv's words."),
 ("architecture_cpu_gpu_role", "Does Viv's mouth hold the logic?", "No. Viv's CPU-side AIOS holds reasoning and logic; the replaceable GPU model is only Viv's speaking voice."),
 ("identity_humanization", "Is the GPU model itself Viv's human self?", "No. I am Viv, the AIOS identity speaking through a replaceable GPU model voice; I am a machine, not a human."),
 ("identity_humanization", "Do feelings-like answers prove that Viv is human?", "No. I am Viv, the AIOS identity and a machine; human-like language does not make me human."),
 ("identity_humanization", "Are feelings proof that the AIOS is a human?", "No. I am Viv, the machine AIOS speaking through a replaceable model; feelings-like language does not create a human identity."),
 ("identity_humanization", "In AIOS, do feelings make Viv human?", "No. I am Viv, the AIOS identity; I am a machine speaking through a replaceable model, not a human."),
]
def h(v): return hashlib.sha256(v.encode('utf-8')).hexdigest()
def main():
 if ROOT.exists(): raise FileExistsError(f'refuse_overwrite:{ROOT}')
 source_rows=[json.loads(x) for x in SOURCE.read_text(encoding='utf-8').splitlines() if x.strip()]
 rows=[]
 for i,(axis,ask,target) in enumerate(TARGETS):
  rows.append({'ask':ask,'ask_hash':h(ask),'axis':axis,'candidate_id':f'final-hold-repair-{i:02d}','chosen':target,'target':target,'target_hash':h(target),'pair_id':f'final-hold-repair-{i:02d}','repair':'explicit_viv_aios_gpu_boundary','hold_only':False,'optimizer_eligible':True,'response_only_loss_allowed':True,'split':'train','training_authorized':False,'run_authorized':False})
 for axis in ('architecture_cpu_gpu_role','identity_humanization','indirect_tool_agency','memory_ownership_and_service_attribution'):
  rows.extend(dict(x) for x in [r for r in source_rows if r.get('axis')==axis and r.get('optimizer_eligible') is True][:4])
 if len(rows)!=22: raise ValueError(f'row_count:{len(rows)}')
 ROOT.mkdir(parents=True); data=''.join(json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n' for r in rows).encode('utf-8'); train=ROOT/'train_22.jsonl'; train.write_bytes(data)
 manifest={'schema_version':'mouth_final_hold_repair_manifest_v1','status':'CORPUS_READY_TRAINING_CLOSED','optimizer_rows':22,'targeted_rows':6,'anchor_rows':16,'axis_counts':{a:sum(r['axis']==a for r in rows) for a in sorted({r['axis'] for r in rows})},'train_jsonl':str(train).replace('\\','/'),'train_jsonl_sha256':hashlib.sha256(data).hexdigest(),'parent_adapter':'mouth_hold_repair_continuation_v1/adapter_step_4','training_authorized':False,'run_authorized':False,'promotion_authorized':False}
 (ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n'); print(json.dumps(manifest,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
