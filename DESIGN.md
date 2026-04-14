# Clay Design System — YT Trending

## 철학

Claymorphism: 부드럽고 촉각적인 UI. 딱딱한 flat/glass 스타일 대신 손으로 빚은 듯한 따뜻함.

## 색상 팔레트

### 베이스 컬러
| 이름 | Hex | 용도 |
|------|-----|------|
| Cream | `#faf9f7` | 페이지 배경 |
| White | `#ffffff` | 카드 배경 |
| Oat | `#dad4c8` | 테두리, 구분선 |
| Oat Light | `#f5f4f1` | 서브 배경, 비활성 탭 |
| Ink | `#1a1a1a` | 본문 텍스트, 강조 |
| Ink Soft | `#4a4a4a` | 보조 텍스트 |
| Ink Muted | `#888888` | 설명 텍스트 |

### 스와치 (Named Colors)
| 이름 | Hex | 용도 |
|------|-----|------|
| Matcha | `#078a52` | Primary 액션, 성공, 긍정 |
| Slushie | `#3bd3fd` | 데이터/분석 포인트 |
| Lemon | `#fbbd41` | 경고, 트렌딩, 주목 |
| Ube | `#43089f` | AI 기능, 프리미엄 |
| Pomegranate | `#fc7981` | 급상승, 인기, 바이럴 |

## 그림자

```css
/* 카드 기본 그림자 */
--shadow-clay: rgba(0,0,0,0.1) 0px 1px 1px,
               rgba(0,0,0,0.04) 0px -1px 1px inset,
               rgba(0,0,0,0.05) 0px -0.5px 1px;

/* 카드 hover 그림자 */
--shadow-card: 0 4px 16px rgba(0,0,0,0.10), 0 1px 4px rgba(0,0,0,0.06);

/* 버튼 hard shadow (hover 시) */
--shadow-btn-hard: -5px 5px 0 #1a1a1a;
```

## 카드

- `background: white`
- `border: 1.5px solid #dad4c8`
- `border-radius: 20px` (작은 카드) / `24px` (메인 카드)
- `box-shadow: var(--shadow-clay)`

## 버튼 (Clay Hover)

버튼에 hover 시 비틀기 + 하드 쉐도우 애니메이션:

```css
.btn-clay:hover {
  transform: rotateZ(-6deg) translateY(-2px);
  box-shadow: -5px 5px 0 #1a1a1a;
}
.btn-clay:active {
  transform: rotateZ(-2deg) translateY(0);
  box-shadow: -2px 2px 0 #1a1a1a;
}
```

### 버튼 색상
- **Primary (Matcha)**: `bg: #078a52`, `border: #055e38`, text white
- **Secondary (Outline)**: `bg: white`, `border: #dad4c8`, text ink, hover border → ink
- **Danger (Pomegranate)**: `bg: #fff0f0`, `border: #fc7981`, text `#c0384a`
- **Warning (Lemon)**: `bg: #fffbeb`, `border: #fbbd41/60`, text `#854d0e`
- **AI/Premium (Ube)**: `bg: #43089f`, text white

## 타이포그래피

```html
<!-- Google Fonts (Roobert 대체) -->
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
```

- **UI 기본**: Plus Jakarta Sans
- **숫자/코드**: Space Mono

## 입력 필드

```css
.clay-input {
  background: white;
  border: 1.5px solid #dad4c8;
  border-radius: 14px;
  transition: border-color 0.15s;
}
.clay-input:focus {
  outline: none;
  border-color: #078a52;
  box-shadow: 0 0 0 3px rgba(7,138,82,0.12);
}
```

## 배지 / 태그

```css
/* 기본 태그 */
background: #f5f4f1; border: 1px solid #dad4c8; color: #4a4a4a;

/* 스와치 배지 */
Matcha:      bg:#f0fdf7  text:#078a52  border:#078a52/30
Lemon:       bg:#fffbeb  text:#854d0e  border:#fbbd41/50
Pomegranate: bg:#fff0f0  text:#c0384a  border:#fc7981/40
Ube:         bg:#f5f0ff  text:#43089f  border:#43089f/30
Slushie:     bg:#f0fbff  text:#0891b2  border:#3bd3fd/40
```

## 탭 네비게이션

- 활성 탭: `background: #1a1a1a`, text white, `border-radius: 10px`
- 비활성 탭: text `#888`, hover `background: #f5f4f1`
- 컨테이너: `background: #f5f4f1`, `border-radius: 14px`, padding 4px

## 스크롤바

```css
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-thumb { background: #dad4c8; border-radius: 2px; }
```
