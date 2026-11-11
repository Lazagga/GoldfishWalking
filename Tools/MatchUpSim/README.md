# Match Up 시뮬레이터 + 환상별 승률 곡선 뷰어

`fantasy_viewer_SPEC.md`(2026-11-11)의 구현. 폴더: `Tools/MatchUpSim/`

## 이번 구현에서 가정한 내용 (명세 §9)

| # | 질문 | 적용한 답 |
|---|---|---|
| Q1 | X축 | `monsters.hp_base`, `act_hp_growth=2.0` 고정. **범위는 명세 기본값 50~100이 아니라 200~1200(간격 100)으로 바꿈** — 아래 "규모 차이" 참고 |
| Q2 | 원본 환상 데이터 | 접근 가능(`Assets/Data/Json/fantasies`, 69종). `import_fantasies.py`로 자동 변환하고, 해석이 필요한 것은 `fantasy_effects.overrides.json`에 직접 적은 근사로 보완 |
| Q3 | 보상 구조(런당 환상 수) | 현재 구조 유지(일반 전투도 환상 확정 획득). 뷰어 상태 배너에 기준선 평균 보유 환상 수를 표시 |
| Q4 | 보상 선택 정책 | 무작위 유지. `policy.fantasy_pick = "random"` 자리만 마련 |
| Q5 | 강제 포함 시점 | 런 시작. `--force-at FLOOR`(전체 층 번호)도 지원 |

### 규모 차이 (중요)
환상별 효과를 넣으면(table 모드) 플레이어가 grade 모드보다 훨씬 강해진다. 시뮬레이터의 피해·체력 수치는
"임시값"인데 환상 수치(새총 +30/타, 닻 -20/타, 쿠키 +300 등)는 게임 원본 값이고, 런당 환상을 많이 얻기 때문이다.

| `act_hp_growth=2.0` | grade 모드 | table 모드 (seed verify, 2000판) |
|---|---|---|
| `hp_base=74` | 승률 9.1%, 평균 30.1층 | 승률 97.5% |
| 승률 10% 지점 | `hp_base≈74` | `hp_base≈660` (평균 도달 9층) |

table 모드에서 승률 10% 지점은 평균 도달이 9층 정도라, 1막에서 대부분 죽고 살아남으면 환상이 쌓여 끝까지 가는 양극화된 분포다.
grade 모드의 분포(2·3막 사망이 대부분)와 모양이 다르다. 그래서 **곡선의 절대 위치보다 환상 간 순서와 방향**만 의미가 있다.
수치 보정(시뮬레이터 임시값을 게임 규모로 맞추기)과 Q3(런당 환상 수)이 다음 결정 사항이다.

### 첫 전체 스캔 결과 (scan1, `hp_base` 200~1200, 점당 3000판, `hp_base=700` 기준)
기준선 승률은 200: 62.8% → 700: 8.0% → 1200: 1.3%, 기준선이 10%와 만나는 지점은 `hp_base≈650`.

- **받는 피해 고정 감소·타격 회복이 압도적**: 포인세티아(받는 피해 -30/타) +85%p, 낫(타격마다 +20) +81%p, 닻(-20/타) +76%p.
  시뮬레이터의 몬스터 1타 피해(1막 평균 약 10, 3막 약 24)가 이 감소량보다 작아 사실상 무적이 된다.
  환상 밸런스 문제라기보다 **시뮬레이터의 몬스터 피해 규모가 게임보다 작다**는 신호일 가능성이 높다.
- 그다음: 동물친구들(타수 +4) +62%p, 병 속의 배 +34%p, 큐대 +28%p, 주판 +20%p, 포도탄 +19%p.
- 음수: 천칭자리 -6.5%p, 사자자리 -5.4%p(둘 다 강한 신호). 천칭자리는 "기본 피해 0 → 200" 조작을 모델링하지 않아 과소평가된 근사다.
- 미모델링 6종은 모두 |Δ| ≤ 1.3%p, CI가 0을 포함하거나 경계에 걸침 (트럼프 카드 +1.3%p는 풀 축소 효과 범위).
- 이 체력대에서는 런이 일찍 끝나 기준선 평균 보유 환상이 약 7~9개로, Q3의 "런당 37개" 문제는 쉬운 설정(낮은 체력)에서만 나타난다.

## 빠른 사용법

```bash
cd Tools/MatchUpSim

# 1) 원본 환상 JSON → 효과 테이블 (원본이나 overrides 를 고친 뒤 다시 실행)
python import_fantasies.py

# 2) 스캔 (중단 후 같은 명령을 다시 실행하면 캐시에서 이어서 진행)
python matchup_sim.py --fantasy-scan --effects fantasy_effects.json \
    --x monsters.hp_base=200:1200:100 --fantasies all --runs 3000 --seed scan1 \
    --set monsters.act_hp_growth=2.0 --workers 11 --out sim_results

# 3) 단일 HTML 뷰어 생성 → sim_results/fantasy_viewer.html 을 더블클릭
python build_viewer.py --data sim_results/fantasy_curves.json
```

그 밖의 사용법:

```bash
# 기존 동작 (grade 모드, 변경 전과 판 단위로 동일)
python matchup_sim.py --seed verify --runs 5000 --set monsters.act_hp_growth=2.0 --set monsters.hp_base=74

# table 모드로 배치 1회, 특정 환상 강제 포함 (여러 개는 쉼표)
python matchup_sim.py --effects fantasy_effects.json --force-fantasy fan_turn_boots,fan_damage_anchor \
    --set monsters.act_hp_growth=2.0 --set monsters.hp_base=660 --runs 3000 --seed s1

# table 모드에서 승률 10% 체력 찾기
python matchup_sim.py --effects fantasy_effects.json --set monsters.act_hp_growth=2.0 \
    --tune monsters.hp_base=50:2000 --target 0.10 --runs 2000 --seed t1
```

성능(이 PC, 12코어): grade 모드 판당 약 1ms, table 모드 판당 약 2~3ms. 전체 스캔(70곡선 x 11점 x 3000판 = 231만 판)은 워커 11개로 약 15분.

## 파일

| 파일 | 역할 |
|---|---|
| `matchup_sim.py` | 시뮬레이터. `effect_mode`(grade/table), 효과 타입, 강제 포함, `--fantasy-scan` 위임 |
| `fantasy_scan.py` | 스캔: 병렬(`multiprocessing`), 점 단위 캐시·재개, 짝지은 통계, CSV/JSON 출력 |
| `import_fantasies.py` | 원본 JSON → `fantasy_effects.json`. 원본이 없으면 `--template` 으로 전부 none 인 템플릿 생성 |
| `fantasy_effects.overrides.json` | 자동 매핑이 안 되거나 해석이 필요한 환상의 수동 근사 (데이터) |
| `fantasy_effects.json` | 생성된 효과 테이블 (69종 전부, `fidelity` 표시) |
| `build_viewer.py`, `viewer_template.html` | 데이터를 내장한 단일 HTML 뷰어 생성 |
| `tests/` | AC1~AC7 테스트. `_matchup_sim_original.py`는 회귀 비교용 변경 전 코드 사본 |
| `sim_results/` | 결과. `fantasy_curves.csv`(누적), `fantasy_curves.json`(최신), `fantasy_scans/`(스캔별 보관), `fantasy_cache/`(캐시, git 제외) |

> `matchup_sim.py`는 저장소 루트에서 이 폴더로 옮겼다.

## 효과 모델

### effect_mode
- `grade`(기본): 기존 동작 그대로. 등급별 개수 x 등급 계수. 결과가 변경 전 코드와 판 단위로 같다(AC1).
- `table`: `fantasy.effects_file`의 환상별 효과만 쓴다. **등급 계수는 쓰지 않는다**(그래야 미모델링 환상이 기준선과 같아진다).
  보상·상점 풀도 효과 테이블에서 만든다(백 32 / 청 24 / 적 13, 단 `available:false` 인 주사기·동물친구들은 풀에서 제외).
- `--effects`를 주면 따로 지정하지 않는 한 table 모드가 된다.

### fidelity (69종: exact 35 · approx 28 · none 6)
- `exact`: 원본 효과를 시뮬레이터 타입으로 그대로 표현.
- `approx`: 근사. `notes`에 방법을 적음. 대부분 "상자 숫자를 시뮬레이터의 기본 피해/몬스터 1타 피해로 근사", "조건을 맞추려는 조작은 미모델링" 류.
- `none`: 미모델링 — 주사위(무작위 선택이라 새로고침 가치 0), 머그잔, 스텐실, 스탬프쿠폰, 사수자리, 트럼프 카드(정책상 효과 0).

데이터와 설명이 어긋나는 환상은 **데이터 값**을 썼고 `notes`에 적었다: 수박(설명 +150 / 데이터 200), 쿠키(+200 / 300),
할인 쿠폰(30% / x0.85), 돛(amount 50.0 을 50%로 해석).

### 효과 타입
같은 타입은 합산(`*_mult` 4종은 곱). 환상 ID로 분기하는 코드는 없다. `when`: `turn_eq`, `turn_ge`, `turn_mod:[m,r]`, `base_same_digits`.
힘 1 = 1타당 피해 1 (몬스터 힘과 같은 단위).

| 분류 | 타입 |
|---|---|
| 내 피해 | `dmg_mult_add`, `dmg_flat`(타격당, `act_scaling`), `dmg_final_mult`(`condition: base_eq_monster_dmg`), `base_dmg_transform`(`op`: mult/digit_min/first_digit/odd_even/zero_set), `hits_add`(`per`: items_held/consecutive_pairs), `combo_same_dmg_stack`, `end_turn_dmg`(`per`: items_held/items_used_battle/hp/digit8), `player_str_add`, `mirror_enemy_str` |
| 이동·소모품 | `moves_per_turn_add`, `moves_per_turn_mult`, `battle_start_moves`, `carry_unused_moves`, `battle_temp_items`, `item_use_refund_chance` |
| 받는 피해·몬스터 | `dmg_taken_flat`, `dmg_taken_mult`(`condition: monster_dmg_ge_player_base`), `dmg_taken_delay`, `def_cut_add`, `monster_dmg_digit_max`, `monster_str_add`, `str_block`, `monster_skip_chance_add`, `enemy_acts_first`, `reflect_on_hit`(`value`/`pct`), `heal_on_deal`, `heal_on_take`, `heal_per_unused_move`, `revive_once`, `battle_start_temp_copy` |
| 전투 밖 | `heal_per_battle`, `item_drop_chance_add`, `item_drop_mult`, `item_gain_bonus`, `rest_heal_mult`, `rest_heal_add`, `rest_extra_uses`, `rest_alt_fantasy`, `shop_price_mult`, `shop_enter_heal`, `shop_moves_add`, `shop_free_items`, `on_acquire_heal`, `acquire_dup_or_void`, `on_acquire_copy_owned`, `combine_into` |

환상 고유의 난수(사자자리·청사진·도장·오르골)는 이벤트 난수와 분리된 스트림을 써서 짝지은 비교가 덜 흔들리게 했다.

### 강제 포함
`fantasy.forced = {"ids": [...], "at": "start" | {"floor": N}}`. `RunState.acquire()`를 거쳐 보유 목록에 들어가므로
보상·상점 후보에서 자동 제외되고 `runs.csv`의 `fantasies` 첫 항목이 된다. **추가형**(보유 수 +1)이다.

## 통계와 해석 주의
- Δ승률은 같은 시드 `i`끼리 `d_i = win_i(환상) − win_i(기준선)`의 평균, se = 표본표준편차/√n, 95% CI = Δ ± 1.96·se.
  강제 포함으로 보상 후보가 달라지면 경로가 곧 갈라지므로 짝짓기 효과는 약하다. 통계는 짝짓기 효과에 의존하지 않는다.
- 점당 3000판에서 구분 가능한 Δ는 대략 ±1~1.5%p. 뷰어 배너에 실제 값을 표시한다.
- 69종 동시 비교: `신호` = CI가 0을 제외, `강한 신호` = |Δ/se| ≥ 3.4(Bonferroni 근사). 95% 신호 중 약 5%는 우연이다.
- **미모델링/효과 없는 환상도 Δ가 정확히 0은 아니다**: 강제 포함하면 그 환상이 보상 후보에서 빠지므로, 그 자리에 다른(효과 있는) 환상이 들어올 수 있다. 이 "풀 축소" 효과는 작지만 양(+)의 방향이다.
- 인형 4종은 장식이지만 동물친구들(타수 +4) **조합 재료**라서 강제 포함하면 조합 확률이 올라 Δ가 양수가 될 수 있다(모델링된 효과).
- 사후 분석(`runs.csv`의 `fantasies` 열로 "X를 가진 판의 승률")은 생존 편향이 있어 만들지 않았다.
- 평활화는 표시 옵션이며 통계에는 영향이 없다.

## 뷰어
- 좌측: 검색, 등급 칩, 정렬(Δ 큰/작은 순, 이름, 등급), 최대 6개 선택(색 + 선 모양 + 마커로 구분), 효과 요약, fidelity 배지, 선택 X의 Δ.
- 상단: Y 지표(승률 / Δ승률 / 평균 도달 층 / 막별 사망률), 선택 X, 목표 승률, 95% CI 밴드, 평활화(표시용).
- 탭: 승률 곡선(호버 툴팁, 클릭으로 X 선택, 등가 체력 이득), 생존 곡선(층별 도달률, 막 경계), 랭킹 표(선택 X / 전 구간 평균, 정렬, 행 클릭으로 추가).
- 상태는 URL 해시(`#f=a,b&m=delta&x=700&t=curve&T=0.1...`)에 저장되어 링크로 공유된다.
- `effect_mode`가 table이 아닌 데이터는 차단 메시지만 표시한다.
- 네트워크 요청 없음, 외부 라이브러리 없음, 라이트/다크 모드 대응.

## 테스트

```bash
cd Tools/MatchUpSim/tests
python -m unittest test_sim -v      # AC1 회귀, AC2 효과 타입 방향(46종 전부), AC3 강제 포함   (~1분)
python -m unittest test_scan -v     # AC4 결정성(워커 1 vs N, 캐시 삭제), AC5 위양성률          (~3분)
python -m unittest test_viewer -v   # AC6 뷰어 스모크 + 스크린샷, AC7 성능 (pip install playwright) (~20초)
```

- AC5는 명세대로 더미 30종을 한 번에 스캔하는 검사와, 더미마다 시드를 따로 쓰는 독립 검사(z²의 평균 ≈ 1)를 함께 둔다.
  더미 30종은 같은 기준선 표본을 공유해 서로 상관되므로 앞의 검사만으로는 약하다.
- 뷰어 테스트는 설치된 Edge(`channel=msedge`)를 쓴다. 다른 브라우저는 환경 변수 `VIEWER_BROWSER_CHANNEL`. 실제 스캔 데이터로 돌리려면 `VIEWER_DATA=sim_results/fantasy_curves.json`.
- 시뮬레이션 의미가 바뀌는 수정을 하면 `matchup_sim.SIM_VERSION`을 올려 캐시를 무효화한다.
