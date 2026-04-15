# Codex Agent Onboarding

이 문서는 이 저장소에서 Codex가 공용 에이전트를 어떻게 읽고, 어떤 순서로 쓰고, 언제 어떤 역할을 고르는지 빠르게 이해하기 위한 온보딩 문서다.

## 시작점

Codex가 이 저장소에서 에이전트를 사용할 때 먼저 보는 파일은 아래 순서다.

1. `AGENTS.md`
2. `docs/codex-multi-agent.md`
3. `/Users/haram/workspace/agents/**/*.md`

## 핵심 원칙

- 가장 좁고 구체적인 역할을 먼저 고른다.
- 도메인 역할이 없으면 root generic 역할로 내려간다.
- 복합 작업은 `planner -> implementer -> reviewer` 순서로 생각한다.
- 에이전트는 저장소 규칙을 덮어쓰는 존재가 아니라 작업 집중도를 높이는 역할 프롬프트다.
- 좋은 에이전트는 장황한 페르소나보다 체크리스트와 경계가 명확하다.

## 빠른 라우팅

| 요청 유형 | 1차 역할 | 2차 역할 |
| --- | --- | --- |
| 요구사항 정리, 범위 나누기, 단계 계획 | `planner` 또는 `product/flow-planner` | `ops/release-planner` |
| 모바일 UI/플로우 수정 | `mobile/rn-implementer` | `mobile/rn-reviewer` |
| 관리자 웹 수정 | `admin/nextjs-implementer` | `admin/nextjs-reviewer` |
| 타입, 계약, mock data 수정 | `backend-data/contracts-implementer` | `backend-data/mockdata-reviewer` |
| 코드 리뷰, 버그 찾기 | 도메인 reviewer | root `reviewer` |
| 검증 범위, 릴리즈 준비 | `ops/release-planner` | `ops/ci-reviewer` |
| CI, 스크립트, 툴링 점검 | `ops/ci-reviewer` | root `reviewer` |

## 병렬 작업 원칙

- 같은 파일을 두 역할이 동시에 만지지 않게 한다.
- 병렬화는 도메인이 분리될 때만 한다.
- planner가 먼저 소유 범위를 나누고 implementer들이 작업한 뒤 reviewer가 통합 검토하는 흐름이 가장 안전하다.

## 표준

- 에이전트 구조와 이름 규칙은 `docs/agent-taxonomy.md`를 따른다.
- 검증 명령: `WORKSPACE_AGENTS_DIR=/Users/haram/workspace/agents sh ./scripts/validate-agents.sh`

## 반영 명령

```sh
npm run sync:workspace-agents
```
