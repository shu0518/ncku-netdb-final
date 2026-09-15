#!/usr/bin/env bash
# ===== Open Track 完整驗證 (從 repo 根目錄執行) =====
SK=skills/open-unittest-shu0518
EX=$SK/scripts/examples
mkdir -p /tmp/ot_logs
HERMES="hermes chat --toolsets skills,terminal --yolo -Q"

run_scenario () {  # $1=example檔名(不含路徑)  $2=tag
  local f=$1 tag=$2 rp=/tmp/ot_logs/r_$2.json log=/tmp/ot_logs/$2.log
  local payload mid ok="" attempt
  payload=$(python3 -c "import json;t=json.load(open('$EX/$f'));t.pop('reference_tests',None);print(json.dumps(t))")
  for attempt in 1 2; do
    rm -f "$rp"
    AIASE_RESULT_PATH="$rp" timeout 300 $HERMES -q "/open-unittest-shu0518 $payload" \
      > "${log}.try$attempt" 2>&1
    if [ -f "$rp" ]; then
      mid=$(python3 -c "import json;r=json.load(open('$rp'));print(r.get('task_id') or 'EMPTY')" 2>/dev/null)
      [ "$mid" != "EMPTY" ] && [ -n "$mid" ] && { ok=1; cp "${log}.try$attempt" "$log"; break; }
    fi
    echo "   ↻ $tag attempt $attempt 失敗(無檔/task_id空),重試…"
  done
  if [ -n "$ok" ]; then
    echo -n "   $tag 實機 → "
    python3 -c "import json;r=json.load(open('$rp'));s=r['self_report'];print('task_id=%s pass_on_ref=%s mutation=%s cov=%s n_tests=%s'%(r['task_id'],s.get('tests_pass_on_reference'),s.get('mutation_score'),s.get('coverage_pct'),s.get('n_tests')))"
  else
    echo "   ❌ $tag 兩次都沒產出有效結果檔(log: ${log}.try*)"
  fi
}

echo "========== [1/4] 三個 scenario 實機跑 (Hermes) =========="
run_scenario s1_clamp.json         s1
run_scenario s2_grade_letter.json  s2
run_scenario s3_is_leap_year.json  s3

echo
echo "========== [2/4] score.py 重算 (staff 評分方式, 由 tests 重算非採信 self_report) =========="
for s in s1:s1_clamp s2:s2_grade_letter s3:s3_is_leap_year; do
  tag=${s%%:*}; base=${s##*:}; rp=/tmp/ot_logs/r_$tag.json
  [ -f "$rp" ] && { echo -n "   $tag → "; \
    python3 $SK/scripts/score.py --task-file $EX/$base.json --result-file "$rp" \
    | python3 -c "import json,sys;v=json.load(sys.stdin);print('passed=%s scenario_score=%s mutation=%s (%s/%s)'%(v['passed'],v['scenario_score'],v['mutation_score'],v['mutants_killed'],v['mutants_total']))"; } \
    || echo "   $tag → (無結果檔, 跳過)"
done

echo
echo "========== [3/4] Staff perturbation 模擬 (改函式名 clamp→bound, 改參數名) =========="
cat > /tmp/ot_logs/perturbed_task.json <<'PEOF'
{"task_id":"open_ut_clamp_perturbed","entry_function":"bound","description":"Constrain v to [low, high]; if low>high the two bounds are swapped first.","code":"def bound(v, low, high):\n    if low > high:\n        low, high = high, low\n    if v < low:\n        return low\n    if v > high:\n        return high\n    return v\n"}
PEOF
PB=$(python3 -c "import json;print(json.load(open('/tmp/ot_logs/perturbed_task.json'))and open('/tmp/ot_logs/perturbed_task.json').read().strip())")
for attempt in 1 2; do
  rm -f /tmp/ot_logs/r_perturbed.json
  AIASE_RESULT_PATH=/tmp/ot_logs/r_perturbed.json timeout 300 $HERMES \
    -q "/open-unittest-shu0518 $PB" > /tmp/ot_logs/perturbed.log.try$attempt 2>&1
  [ -f /tmp/ot_logs/r_perturbed.json ] && \
    python3 -c "import json;r=json.load(open('/tmp/ot_logs/r_perturbed.json'));exit(0 if r.get('task_id') else 1)" 2>/dev/null && break
  echo "   ↻ perturbed attempt $attempt 失敗,重試…"
done
echo -n "   perturbed (renamed) → "
python3 $SK/scripts/score.py --task-file /tmp/ot_logs/perturbed_task.json --result-file /tmp/ot_logs/r_perturbed.json \
  | python3 -c "import json,sys;v=json.load(sys.stdin);print('passed=%s mutation=%s — 改名後仍可評 = anti-hardcoding 成立'%(v['passed'],v['mutation_score']))" 2>/dev/null \
  || echo "(無結果檔)"

echo
echo "========== [4/4] Anti-gameable 反證 (爛測試: 無斷言 + assert True) =========="
cat > /tmp/ot_logs/gameable.py <<'GEOF'
def test_smoke():
    clamp(5, 0, 10)
def test_trivial():
    assert True
GEOF
echo -n "   gameable tests vs s1 → "
python3 $SK/scripts/score.py --task-file $EX/s1_clamp.json --tests-file /tmp/ot_logs/gameable.py \
  | python3 -c "import json,sys;v=json.load(sys.stdin);print('coverage=%s%% 但 mutation=%s, passed=%s — 覆蓋率灌水無法得分'%(v['coverage_pct'],v['mutation_score'],v['passed']))"

echo
echo "========== 本機 metric self-test (3 scenario 一致性) =========="
python3 $SK/scripts/score.py --self-test

echo
echo "所有 log 在 /tmp/ot_logs/  (report §4.4 證據)"
