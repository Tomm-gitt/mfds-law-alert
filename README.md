# MFDS Law Alert

식품의약품안전처(MFDS) RSS를 모니터링하여 키워드 감지 결과를 이메일로 발송하는 자동화 시스템입니다.

## 기능

- 매일 오전 5시(KST) GitHub Actions 자동 실행
- 3개 RSS 게시판은 키워드 필터링 후 감지 항목만 알림
- `본회의 통과 식의약 법률` RSS는 키워드 없이 신규 게시물 전체 알림
- 중복 발송 방지를 위해 `sent_items.json`으로 발송 이력 관리
- 신규 감지 항목이 없으면 메일 미발송

## 감지 키워드

- 식품
- 표시
- 광고
- 화장품
- 인체

## 모니터링 대상 RSS

1. 입법/행정예고: `http://www.mfds.go.kr/www/rss/brd.do?brdId=data0009`
2. 제·개정고시: `http://www.mfds.go.kr/www/rss/brd.do?brdId=data0008`
3. 법, 시행령, 시행규칙: `http://www.mfds.go.kr/www/rss/brd.do?brdId=data0003`
4. 본회의 통과 식의약 법률: `http://www.mfds.go.kr/www/rss/brd.do?brdId=relaw0001`

## 환경 변수 (GitHub Secrets)

- `EMAIL_USER`: Gmail 주소
- `EMAIL_PASSWORD`: Gmail 앱 비밀번호
- `EMAIL_TO`: 수신 이메일 주소

## 실행 방법 (로컬)

```bash
pip install -r requirements.txt
python monitor.py
```

## GitHub Actions 스케줄

- 파일: `.github/workflows/schedule.yml`
- cron: `0 20 * * *`
- UTC 20:00 = KST 다음날 05:00

## 메일 제목

- 신규 감지 항목이 있을 때: `[식약처 법령 알림] 신규 법령정보 감지`
- 신규 감지 항목이 없을 때: 메일 미발송
