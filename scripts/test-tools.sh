#!/usr/bin/env bash
# Curls every tool route against a locally running `npm run dev` server
# (default http://localhost:3000) and prints each response.
#
# Expected values below are transcribed from FAULTS.md / verify.md so a
# mismatch is obvious by eye. Requires `jq` for pretty-printing; falls back
# to raw output if it isn't installed.

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:3000}"

pp() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  elif command -v node >/dev/null 2>&1; then
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{console.log(JSON.stringify(JSON.parse(d),null,2))}catch(e){console.log(d)}})"
  else
    cat
  fi
}

hr() { printf '\n=============================================================\n'; }

hr
echo "1) get_failure_summary"
echo "   Expected: 9996 total attempts, 396 failure rows, 294 unique failed tasks"
echo "   (oom=334 rows/232 tasks, texture_io=14/14, and 5 residual classes summing to 48 rows/48 tasks)"
curl -s -m 60 "$BASE_URL/api/tools/get-failure-summary" | pp

hr
echo "2) classify_error_samples(error_class=oom, limit=2)"
echo "   Expected: 334 rows / 232 unique tasks, 5 distinct shots (4 hair shots + shot_047), groups A/B/C"
curl -s -m 60 "$BASE_URL/api/tools/classify-error-samples?error_class=oom&limit=2" | pp

hr
echo "2b) classify_error_samples(error_class=texture_io, limit=3)"
echo "   Expected: 14 rows / 14 unique tasks"
curl -s -m 60 "$BASE_URL/api/tools/classify-error-samples?error_class=texture_io&limit=3" | pp

hr
echo "3) test_dimension_concentration(node_group) restricted to error_class=oom"
echo "   Expected: group B holds 278 of 334 (83.2%) against 29.9% expected share -> strong concentration"
curl -s -m 60 "$BASE_URL/api/tools/test-dimension-concentration?dimension=node_group&error_class=oom" | pp

hr
echo "3b) test_dimension_concentration(shot_id) excluding oom,texture_io (the residual + license/disk/etc are lumped; excluding oom+texture_io isolates the 48-row residual)"
echo "   Expected: 48 failure rows, no value concentrates above base rate"
curl -s -m 60 "$BASE_URL/api/tools/test-dimension-concentration?dimension=shot_id&exclude_error_class=oom,texture_io" | pp

hr
echo "3c) test_dimension_concentration(time_bucket) restricted to error_class=texture_io"
echo "   Expected: strongest 10-min bucket 02:10:00 holds 13/14 (the 02:08:24-02:18:36 stall straddles"
echo "   that bucket edge) -> strong concentration; contiguous_window reports 14 of 14 in a boundary-"
echo "   independent 11-minute span (02:08:24 to 02:18:36)"
curl -s -m 60 "$BASE_URL/api/tools/test-dimension-concentration?dimension=time_bucket&error_class=texture_io" | pp

hr
echo "4) check_success_elsewhere(shot_id, shot_012, split_by=node_group)"
echo "   Expected: fails in B (~45.7%), succeeds in A and C (~0.6%, ~1.4%) -> uneven, node_group named as the split"
curl -s -m 60 "$BASE_URL/api/tools/check-success-elsewhere?dimension=shot_id&value=shot_012&split_by=node_group" | pp

hr
echo "4b) check_success_elsewhere(shot_id, shot_012, split_by=renderer_version)"
echo "   Expected: fails in 7.3.1 (~50.9%), succeeds in 7.3.0 (~0.9%) -> the real axis, not node_group per se"
curl -s -m 60 "$BASE_URL/api/tools/check-success-elsewhere?dimension=shot_id&value=shot_012&split_by=renderer_version" | pp

hr
echo "4c) check_success_elsewhere(shot_id, shot_047, split_by=node_group)"
echo "   Expected: A/B/C all comparable (~38.5%, ~35.0%, ~26.4%) -> 'does not escape by changing node_group'"
curl -s -m 60 "$BASE_URL/api/tools/check-success-elsewhere?dimension=shot_id&value=shot_047&split_by=node_group" | pp

hr
echo "4d) check_success_elsewhere(shot_id, shot_003, split_by=node_group) -- REGRESSION TEST"
echo "   shot_003 has no assigned fault (1 incidental failure in A, 0 in B/C)."
echo "   Expected: summary says background noise / nothing meaningful, NOT a node-group split."
curl -s -m 60 "$BASE_URL/api/tools/check-success-elsewhere?dimension=shot_id&value=shot_003&split_by=node_group" | pp

hr
echo "5) query_similar_past_incidents(error_class=texture_io)"
echo "   Expected: includes inc_20260814_001 (2026-08-14 NFS texture filer stall), plus near-misses."
echo "   No dimension_signature supplied -> zero keyword overlap possible, so every incident whose"
echo "   error_class is texture_io is match_strength=weak (error class only) and every non-texture_io"
echo "   incident is also weak (class differs). No 'title' field in the response (removed by design —"
echo "   a past incident's title names a different problem, so it's dropped everywhere)."
curl -s -m 60 "$BASE_URL/api/tools/query-similar-past-incidents?error_class=texture_io" | pp

hr
echo "5b) query_similar_past_incidents(error_class=oom, dimension_signature=node_group hair shader memory regression)"
echo "   Expected: past hair-shader / memory-regression incidents rank above unrelated oom incidents,"
echo "   with match_strength=strong or partial (>=1 keyword overlap on 'hair'/'shader'/'group'/etc.)."
echo "   inc_20260805_001 (the subdivision/geometry near-miss, unrelated to this signature) still"
echo "   surfaces in the top 4 on error_class alone, but now comes back match_strength=weak, with a"
echo "   match_note stating plainly it's a comparison, not an explanation -- root_cause is still"
echo "   returned in full (it's still instructive as a near-miss), but there's no 'title' field to"
echo "   accidentally borrow language from, and the summary states how many of the 4 are weak matches."
curl -s -m 60 "$BASE_URL/api/tools/query-similar-past-incidents?error_class=oom&dimension_signature=node%20group%20hair%20shader%20memory%20regression" | pp

hr
echo "6) get_farm_capacity(window_hours=8)"
echo "   Expected: A=40 nodes/64GB/7.3.0, B=30 nodes/64GB/7.3.1 (current fleet, post-incident), C=30 nodes/128GB/7.3.0"
echo "   100 nodes total, 800 available node-hours at 8h window"
curl -s -m 60 "$BASE_URL/api/tools/get-farm-capacity?window_hours=8" | pp

hr
echo "Done."
