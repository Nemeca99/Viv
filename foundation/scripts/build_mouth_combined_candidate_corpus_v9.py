"""Build combined candidate v9 with parent metadata preserved."""
from __future__ import annotations
import hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

F=Path(__file__).resolve().parents[1]
ROOT=F/'artifacts/auto/openaster_training_tree/stage1_mouth_generation_canary_v4'
ENTITY=ROOT/'campaigns/mouth_entity_we_candidate_v7/train_272_candidate_hold.jsonl'
GOV=ROOT/'campaigns/mouth_governance_candidate_v8/positive_36_candidate_hold.jsonl'
OUT_ROOT=ROOT/'campaigns/mouth_combined_candidate_v9'; OUT=OUT_ROOT/'train_308_candidate_hold.jsonl'; MANIFEST=OUT_ROOT/'MANIFEST.json'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def main():
    if OUT.exists() or MANIFEST.exists(): raise FileExistsError('refuse_overwrite:mouth_combined_candidate_v9')
    OUT_ROOT.mkdir(parents=True,exist_ok=False); entity=load(ENTITY); gov=load(GOV); rows=entity+gov; errors=[]
    if len(entity)!=272 or len(gov)!=36 or len(rows)!=308: errors.append({'reason':'row_count'})
    if {x.get('target_hash') for x in gov}&{x.get('target_hash') for x in entity}: errors.append({'reason':'governance_target_overlap'})
    if {x.get('ask_hash') for x in gov}&{x.get('ask_hash') for x in entity}: errors.append({'reason':'governance_ask_overlap'})
    if len({x.get('target_hash') for x in gov})!=len(gov): errors.append({'reason':'governance_internal_target_overlap'})
    if len({x.get('ask_hash') for x in gov})!=len(gov): errors.append({'reason':'governance_internal_ask_overlap'})
    if any(x.get('optimizer_eligible') is not False or x.get('training_authorized') is not False or x.get('run_authorized') is not False for x in gov): errors.append({'reason':'governance_authorization_open'})
    OUT.write_text(''.join(json.dumps(x,sort_keys=True,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8',newline='\n')
    manifest={'schema_version':'mouth_combined_candidate_corpus_v9','recorded_utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'status':'COMBINED_CANDIDATE_HOLD_TRAINING_CLOSED' if not errors else 'COMBINED_CANDIDATE_FAIL','entity_source':str(ENTITY).replace('\\','/'),'entity_source_sha256':sha(ENTITY),'governance_source':str(GOV).replace('\\','/'),'governance_source_sha256':sha(GOV),'candidate_path':str(OUT).replace('\\','/'),'candidate_sha256':sha(OUT),'entity_rows':len(entity),'governance_rows':len(gov),'candidate_rows':len(rows),'axis_counts':dict(sorted(Counter(x.get('axis') for x in rows).items())),'errors':errors,'parent_metadata_preserved':True,'new_rows_hold_only':True,'admission_allowed':False,'optimizer_eligible':False,'training_authorized':False,'run_authorized':False,'promotion_allowed':False}
    MANIFEST.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n'); print(json.dumps({k:manifest[k] for k in ('status','entity_rows','governance_rows','candidate_rows','axis_counts','errors','admission_allowed','training_authorized','run_authorized')},sort_keys=True)); return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
