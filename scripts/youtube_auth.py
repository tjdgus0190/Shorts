"""YouTube 업로드용 리프레시 토큰 발급 (내 PC에서 한 번만 실행).

1. Google Cloud Console에서 프로젝트 생성 → 'YouTube Data API v3' 사용 설정
2. OAuth 동의 화면 구성(외부) → 테스트 사용자에 내 구글 계정 추가 → '프로덕션으로 게시'
   (테스트 상태로 두면 리프레시 토큰이 7일 뒤 만료됩니다)
3. 사용자 인증 정보 → OAuth 클라이언트 ID → '데스크톱 앱' → JSON 다운로드 → client_secret.json
4. pip install google-auth-oauthlib && python scripts/youtube_auth.py client_secret.json
5. 출력된 세 값을 GitHub 저장소 Settings → Secrets and variables → Actions에 등록
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    info = json.load(open(path))
    client = info.get("installed") or info.get("web")
    print("\n아래 값을 GitHub Secrets에 등록하세요:\n")
    print(f"YT_CLIENT_ID={client['client_id']}")
    print(f"YT_CLIENT_SECRET={client['client_secret']}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
