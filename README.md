# Shorts Factory 🎬

매일 한 편의 한국어 유튜브 쇼츠를 **자동으로 기획·제작·검수·업로드**하는 멀티 에이전트 파이프라인입니다.
GitHub Actions에서 매일 실행되고, 결과는 GitHub Pages 대시보드에서 한눈에 확인할 수 있습니다.

```
매일 17:00 KST (GitHub Actions)
  │
  ├─ 📈 마케터   Google 트렌드(한국) 실시간 검색어 → 민감 주제 필터 → 쇼츠 주제 10개 보고서
  ├─ 📝 기획자   보고서에서 1개 선정 → 훅·장면별 대본·이미지 프롬프트 (재미 최우선)
  ├─ 🎨 제작자   장면 이미지 생성 → 켄번스(줌/팬) 모션 클립 → 러프컷
  ├─ 🎙 이펙터   TTS 내레이션 + 단어 단위 하이라이트 자막 + 상단 문구 + BGM → 최종 영상
  ├─ ✅ QA       길이·해상도·음량 자동 측정 + 프레임을 직접 보고 재미·품질·안전성 채점
  │              └ 불합격이면 원인 담당(기획자/제작자/이펙터)에게 피드백과 함께 재작업 (최대 2회)
  └─ 📤 업로드   YouTube Data API (AI 생성 콘텐츠 표시 포함)
       └ 영상은 GitHub Release에 보관, 결과는 data/에 커밋 → 대시보드 갱신
```

## 비용: 0원 (Claude Pro 구독만 사용)

| 역할 | 사용 서비스 | 비용 |
|---|---|---|
| 마케터·기획자·QA (LLM) | **Claude Code CLI + Pro 구독 토큰**. 실패 시 Gemini API 무료 티어로 대체 | Pro 구독 사용량 안에서 처리 (하루 4~8회 호출) |
| 트렌드 | Google 트렌드 RSS (`trends.google.com/trending/rss?geo=KR`) | 무료 |
| 이미지 | **Cloudflare Workers AI FLUX.1 schnell** (하루 10,000 뉴런, 약 100장) → Pollinations → 텍스트 카드 | 무료 |
| 음성 | Microsoft Edge TTS (`edge-tts`, `ko-KR-SunHiNeural`) | 무료 |
| 편집 | FFmpeg | 무료 |
| 실행·대시보드 | GitHub Actions + GitHub Pages (공개 저장소) | 무료 |

> 참고: Gemini API는 2026년 기준 **이미지 생성 모델이 무료 티어에서 제공되지 않아** Cloudflare를 기본으로 씁니다.
> Gemini 무료 키는 텍스트 LLM 예비용으로만 쓰입니다(선택).

## 설정 방법

### 1. 시크릿 등록 (Settings → Secrets and variables → Actions)

| 시크릿 | 필수 | 발급 방법 |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | ✅ | 내 PC에서 `claude setup-token` 실행 → 출력된 토큰 |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | 강력 권장 | [Cloudflare](https://dash.cloudflare.com) 무료 가입 → 우측 Account ID 복사 → My Profile → API Tokens → *Workers AI* 템플릿으로 토큰 생성 |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | 업로드 시 | `scripts/youtube_auth.py` 상단 안내대로 한 번 실행 |
| `GEMINI_API_KEY` | 선택 | [Google AI Studio](https://aistudio.google.com/apikey) 무료 키 (Claude 실패 시 대체) |
| `POLLINATIONS_TOKEN` | 선택 | Pollinations 토큰 (익명 사용 시 워터마크·속도 제한) |

### 2. GitHub Pages 켜기
Settings → Pages → **Source: GitHub Actions** 선택.
대시보드 주소: `https://<사용자명>.github.io/Shorts/`

### 3. main 브랜치에 머지
예약 실행(cron)은 **기본 브랜치(main)에 있는 워크플로만** 동작합니다.

### 4. 첫 실행
Actions → **daily-shorts** → *Run workflow*
- `mock` 체크: 키 없이 전체 흐름만 확인
- `upload` 해제: 업로드 없이 영상만 생성

## YouTube 업로드 관련 주의

- **API 감사 전에는 영상이 비공개로 잠깁니다.** 2020년 이후 만든 미감사 API 프로젝트로 업로드한 영상은 YouTube가 강제로 비공개 처리합니다.
  그래서 `config.yaml`의 `upload.privacy`가 기본 `private`입니다. 대시보드에서 확인한 뒤 YouTube Studio에서 공개로 바꾸거나,
  [YouTube API 감사](https://support.google.com/youtube/contact/yt_api_form)를 신청하세요.
- OAuth 동의 화면을 **테스트** 상태로 두면 리프레시 토큰이 7일 뒤 만료됩니다. **프로덕션으로 게시**하세요(본인만 쓰면 검수 없이 가능).
- AI 생성물이므로 `containsSyntheticMedia: true`로 표시합니다.
- 비슷한 템플릿을 대량으로 반복하면 YouTube 파트너 프로그램(수익화)에서 '반복적/비진정성 콘텐츠'로 판단될 수 있습니다.
  프롬프트(`shorts/prompts/`)를 주기적으로 다듬어 포맷을 다양하게 유지하세요.

## 로컬 실행

```bash
sudo apt-get install -y ffmpeg fonts-noto-cjk
pip install -r requirements.txt
python -m shorts run --mock --no-upload          # 키 없이 흐름 확인
python -m shorts run --no-upload                 # 실제 생성 (claude 로그인 또는 GEMINI_API_KEY 필요)
python -m pytest tests
```
결과물: `runs/<날짜>/final.mp4`(영상), `runs/<날짜>/*.json`(에이전트별 산출물), `data/runs/<날짜>.json`(대시보드 요약)

대시보드 미리보기: `mkdir -p _site && cp -r dashboard/* _site && cp -r data _site/ && python -m http.server -d _site`

## 커스터마이징

- `config.yaml`: 업로드 시간 외 거의 모든 설정 (목소리, 말 속도, QA 합격 점수, 재시도 횟수, 민감 키워드, 공개 범위)
- `shorts/prompts/*.md`: 마케터·기획자·QA의 판단 기준 (채널 톤을 바꾸려면 여기를 수정)
- `assets/bgm/`: 저작권 문제없는 mp3를 넣어두면 무작위로 BGM이 깔립니다 (YouTube 오디오 보관함 음원 권장)
- 업로드 시간: `.github/workflows/daily-shorts.yml`의 `cron` (UTC 기준)

## 구조

```
shorts/
  agents/   marketer.py planner.py producer.py effector.py qa.py uploader.py
  tools/    trends.py images.py tts.py subtitles.py video.py fonts.py
  prompts/  marketer.md planner.md qa.md
  llm.py    Claude CLI / Gemini / mock 래퍼
  pipeline.py  오케스트레이션 + QA 재작업 루프 + 대시보드 데이터
dashboard/  정적 대시보드 (GitHub Pages)
data/       실행 결과 요약 (Actions가 매일 커밋)
```
