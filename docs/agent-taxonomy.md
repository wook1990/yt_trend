# Agent Taxonomy Standard

이 문서는 `workspace/agents`를 여러 프로젝트에서 일관되게 쓰기 위한 엄격한 표준이다.

## 목표

- 역할 이름만 보고 용도를 바로 알 수 있게 한다.
- 도메인과 역할을 분리해서 찾기 쉽게 만든다.
- Codex, Claude, Gemini에서 같은 공용 원본을 안정적으로 재사용한다.

## 루트 구조

공용 루트는 아래처럼 고정한다.

```text
/Users/haram/workspace/agents/
  planner.md
  implementer.md
  reviewer.md
  mobile/
  admin/
  backend-data/
  backend-api/
  desktop/
  data-science/
  product/
  ops/
```

## 허용 도메인

- `mobile`
- `admin`
- `backend-data`
- `backend-api`
- `desktop`
- `data-science`
- `product`
- `ops`

새 도메인을 추가하려면 먼저 이 문서와 검증 스크립트를 같이 바꾼다.

## 허용 역할

- `planner`
- `implementer`
- `reviewer`

모든 전문 에이전트는 파일명 끝이 위 세 역할 중 하나로 끝나야 한다.

예:
- `rn-implementer.md`
- `nextjs-reviewer.md`
- `flow-planner.md`

## 파일명 규칙

- 소문자 kebab-case만 허용
- 공백 금지
- 밑줄 금지
- 확장자는 `.md`
- 루트 generic 파일은 아래 3개만 허용
  - `planner.md`
  - `implementer.md`
  - `reviewer.md`

## frontmatter 규칙

모든 파일은 아래 메타데이터를 가져야 한다.

```md
---
name: rn-implementer
title: React Native Implementer
description: Implement mobile app changes in Expo and React Native.
---
```

규칙:
- `name`은 파일명과 같아야 한다
- `title`은 사람에게 읽히는 역할명이어야 한다
- `description`은 한 문장으로 역할 목적을 설명해야 한다

## 역할 설계 규칙

- generic root 에이전트는 넓은 범위의 기본 역할만 맡는다.
- 도메인 에이전트는 특정 앱, 계층, 운영 영역에만 집중한다.
- 한 파일은 하나의 주 역할만 가진다.
- 구현자와 리뷰어는 반드시 다른 체크리스트를 가져야 한다.
- planner는 설계와 순서화에 집중하고 구현 디테일을 과도하게 포함하지 않는다.

## 권장 패턴

- 모바일 앱 수정
  - `mobile/*-implementer`
  - `mobile/*-reviewer`
- 관리자 웹 수정
  - `admin/*-implementer`
  - `admin/*-reviewer`
- 타입/데이터 구조
  - `backend-data/*-implementer`
  - `backend-data/*-reviewer`
- 백엔드 API, 서비스, DB 연동
  - `backend-api/*-implementer`
  - `backend-api/*-reviewer`
- 데스크톱 앱, 로컬 클라이언트
  - `desktop/*-implementer`
  - `desktop/*-reviewer`
- 분석, 모델, 데이터 실험
  - `data-science/*-implementer`
  - `data-science/*-reviewer`
  - `data-science/*-planner`
- 제품 흐름
  - `product/*-planner`
- CI/릴리즈/도구
  - `ops/*-reviewer`
  - `ops/*-planner`

## 금지 패턴

- 한 파일에 planning, implementation, review를 전부 섞는 것
- 도메인 폴더 없이 특수 목적 파일을 루트에 두는 것
- 파일명과 `name`이 다른 것
- 설명이 너무 일반적이어서 다른 에이전트와 구분이 안 되는 것

## 검증

아래 명령으로 표준 준수 여부를 검사한다.

```sh
WORKSPACE_AGENTS_DIR=/Users/haram/workspace/agents sh ./scripts/validate-agents.sh
WORKSPACE_AGENTS_DIR=/Users/haram/workspace/agents sh ./scripts/lint-agents.sh
```
