# 싱싱마켓 AWS 배포 가이드

구조: **사용자 → Nginx(80) → Gunicorn → Django → MariaDB(MySQL)**, 결제는 토스페이먼츠, 상품 이미지는 S3(선택).
처음이면 2~3시간 잡으세요. 각 단계마다 "왜 하는지"를 먼저 적고, 그다음 할 일을 적었어요.

---

## 0. AWS 계정 정리 (처음 한 번)

### 0-1. 루트 계정에 MFA 걸기
**왜?** 처음 가입할 때 만든 계정(이메일 로그인)이 '루트 계정'이에요. 결제 정보까지 모든 권한을 가진 마스터키라서, 비밀번호가 새면 계정 전체가 넘어가요. 그래서 2단계 인증(MFA)을 걸고, 평소에는 쓰지 않아요.
- 콘솔 오른쪽 위 계정 이름 → **보안 자격 증명** → **MFA 디바이스 할당** → 휴대폰 인증 앱(Google Authenticator 등)으로 QR 등록

### 0-2. 평소에 쓸 IAM 사용자 만들기
**왜?** IAM 사용자는 루트 계정 아래에 만드는 '직원 계정'이에요. 평소 작업은 이 계정으로 하고, 필요하면 권한을 줄이거나 지울 수 있어요. 실무에서도 루트 계정으로 작업하지 않는 게 기본 원칙이에요.
1. 콘솔 검색창에 **IAM** → 왼쪽 **사용자** → **사용자 생성**
2. 사용자 이름(예: `admin-yourname`) 입력, **AWS Management Console에 대한 사용자 액세스 권한 제공** 체크 → **IAM 사용자를 생성하고 싶음** 선택 → 비밀번호 직접 지정
3. 권한 설정: **직접 정책 연결** → `AdministratorAccess` 체크 → 생성
   (개인 실습이라 관리자 권한을 주지만, 회사라면 필요한 권한만 주는 게 원칙이에요)
4. 완료 화면의 **콘솔 로그인 URL**(`https://계정ID.signin.aws.amazon.com/console`)을 저장
5. 루트 계정 로그아웃 → 그 URL로 IAM 사용자 로그인 → 이 사용자에도 MFA 걸기

> 액세스 키(Access Key)는 만들지 않아요. 서버가 S3를 쓸 때는 9단계의 **IAM 역할**을 써서 키를 서버에 두지 않습니다.

### 0-3. 요금 알림 걸기
**왜?** 프리 티어를 넘거나 리소스를 끄는 걸 잊으면 요금이 나와요. 미리 알림을 받으면 사고를 막을 수 있어요.
- 검색창에 **Billing and Cost Management** → **예산** → **예산 생성** → 템플릿 **월별 비용 예산** → 금액 예: 5달러, 알림 받을 이메일 입력 → 생성

### 0-4. 리전을 서울로
**왜?** 리전은 서버가 실제로 있는 지역이에요. 한국 사용자 대상이면 서울이 가장 빠르고, 리소스는 리전별로 따로 보여서 리전이 바뀌면 "서버가 사라졌다"고 착각하기 쉬워요.
- 콘솔 오른쪽 위 리전을 **아시아 태평양(서울) ap-northeast-2**로

### 0-5. 토스페이먼츠 테스트 키 받기
**왜?** 결제창을 띄우고(클라이언트 키) 서버에서 결제를 승인하는(시크릿 키) 데 필요해요. 테스트 키는 사업자 없이도 발급돼요.
- [개발자센터](https://developers.tosspayments.com) 가입 → **API 키** → **결제위젯 연동 키**의 `test_gck_...`, `test_gsk_...` 복사
- 시크릿 키는 비밀번호처럼 다뤄요. 코드나 깃허브에 올리지 않고 서버의 `.env`에만 넣어요.

---

## 1. EC2 인스턴스 만들기 (콘솔)
**왜?** EC2는 AWS에서 빌리는 가상 컴퓨터예요. 여기에 웹 서버, Django, DB를 모두 올려요.

EC2 → **인스턴스 시작**
- **이름**: `ssingssing-web`
- **AMI**: Amazon Linux 2023 (AWS가 관리하는 리눅스)
- **인스턴스 유형**: '프리 티어 사용 가능' 표시가 있는 것 (t2.micro 또는 t3.micro)
- **키 페어**: 새로 만들기 → `.pem` 파일 다운로드. 서버 접속 열쇠라서 잃어버리면 다시 받을 수 없어요.
- **네트워크 설정 → 보안 그룹 생성**: 보안 그룹은 서버 앞의 방화벽이에요. 필요한 문만 열어요.
  - SSH(22): **내 IP** — 서버 관리용이라 나만 접속
  - HTTP(80): **0.0.0.0/0** — 손님 누구나 쇼핑몰 접속
  - 3306(DB)은 열지 않아요. DB는 서버 안에서만 쓰니까 외부에 열 이유가 없어요.
- **스토리지**: 20GB (프리 티어는 30GB까지 무료)

**(권장) 탄력적 IP 연결**: EC2를 껐다 켜면 퍼블릭 IP가 바뀌어요. 탄력적 IP를 붙이면 주소가 고정돼요.
EC2 → 탄력적 IP → 할당 → 작업 → 주소 연결 → 내 인스턴스. (퍼블릭 IPv4는 프리 티어 범위를 넘으면 시간당 소액 과금)

**접속**: 인스턴스 선택 → **연결** → **EC2 Instance Connect** → 연결 (브라우저 터미널).
SSH 소스를 '내 IP'로 막아 두면 브라우저 접속이 안 될 수 있어요. 그땐 내 PC 터미널에서 `ssh -i 키.pem ec2-user@퍼블릭IP` 로 접속하세요.

---

## 2. 기본 프로그램 설치 + 메모리 보강
**왜?** 새 서버는 빈 컴퓨터라 Python, 웹 서버(Nginx), DB(MariaDB)를 설치해야 해요. 프리 티어 서버는 메모리가 1GB라 DB와 Django를 같이 돌리면 부족할 수 있어서, 디스크 일부를 메모리처럼 쓰는 스왑을 추가해요.
```bash
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip nginx mariadb105-server unzip
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
```

## 3. DB 만들기
**왜?** 회원, 상품, 주문 정보를 저장할 공간이에요. MariaDB는 MySQL과 같은 방식으로 쓰는 DB예요. 쇼핑몰 전용 DB 사용자를 따로 만들어, 그 DB에만 권한을 줘요.
```bash
sudo systemctl enable --now mariadb      # DB 켜기 + 재부팅 시 자동 시작
sudo mysql_secure_installation           # root 비밀번호 설정, 나머지 질문은 모두 Y
sudo mysql -u root -p
```
```sql
CREATE DATABASE ssingssing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'shop'@'localhost' IDENTIFIED BY '여기에_DB_비밀번호';
GRANT ALL PRIVILEGES ON ssingssing.* TO 'shop'@'localhost';
GRANT ALL PRIVILEGES ON test_ssingssing.* TO 'shop'@'localhost';   -- manage.py test 용 임시 DB
FLUSH PRIVILEGES;
EXIT;
```

## 4. 코드 올리기
**왜?** 내 PC에 있는 쇼핑몰 코드를 서버로 옮기고, 필요한 파이썬 라이브러리를 설치해요. `venv`는 이 프로젝트 전용 파이썬 공간이라 다른 프로그램과 섞이지 않아요.

내 PC 터미널(키 파일과 zip이 있는 폴더)에서:
```bash
scp -i 키.pem ssingssing.zip ec2-user@퍼블릭IP:~
```
EC2에서:
```bash
cd ~ && unzip ssingssing.zip -d ssingssing && cd ssingssing
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 5. 환경 변수(.env) 설정
**왜?** 비밀번호와 키는 코드에 직접 쓰면 유출 위험이 있어서, 서버에만 있는 `.env` 파일에 따로 둬요.
```bash
cp .env.example .env
python3.11 -c "import secrets; print(secrets.token_urlsafe(50))"   # 출력된 값을 DJANGO_SECRET_KEY에
nano .env
chmod 600 .env                                                     # 나만 읽을 수 있게
```
채울 값: `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`(퍼블릭 IP), `CSRF_TRUSTED_ORIGINS`(`http://퍼블릭IP`), `DB_PASSWORD`, `TOSS_CLIENT_KEY`, `TOSS_SECRET_KEY`
(nano 저장: Ctrl+O → Enter, 종료: Ctrl+X)

## 6. DB 테이블 만들기 + 관리자 계정
**왜?** `migrate`는 코드에 정의한 회원·상품·주문 테이블을 DB에 실제로 만들어요. `collectstatic`은 CSS·JS를 한 폴더에 모아 Nginx가 빠르게 보내게 해요.
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_products        # 샘플 상품 8개 (원치 않으면 생략)
python manage.py createsuperuser      # 쇼핑몰 관리자 계정 (AWS IAM과는 별개)
python manage.py test orders          # 자동 테스트 5개가 OK면 정상
```

## 7. Gunicorn 켜기 (Django 실행기)
**왜?** Django를 실제 서비스로 돌리는 프로그램이에요. systemd에 등록하면 서버가 재부팅되거나 프로그램이 죽어도 자동으로 다시 켜져요.
```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/ssingssing.service
sudo systemctl daemon-reload
sudo systemctl enable --now ssingssing
sudo systemctl status ssingssing      # active (running) 이면 성공 (q로 나가기)
```

## 8. Nginx 켜기 (웹 서버)
**왜?** 손님의 요청을 가장 먼저 받는 문지기예요. 이미지·CSS는 직접 보내고, 나머지는 Gunicorn에 넘겨요.
```bash
sed -i 's/server_name _;/server_name 퍼블릭IP;/' deploy/nginx.conf   # 기본 환영 페이지 대신 쇼핑몰이 뜨도록
sudo cp deploy/nginx.conf /etc/nginx/conf.d/ssingssing.conf
chmod 711 /home/ec2-user               # Nginx가 static 폴더를 읽을 수 있게
sudo nginx -t                          # 설정 문법 검사 (successful 확인)
sudo systemctl enable --now nginx && sudo systemctl restart nginx
```
브라우저에서 `http://퍼블릭IP` → 쇼핑몰, `http://퍼블릭IP/manage/` → 관리자.

## 9. 테스트 결제
회원가입 → 상품 담기 → 주문서 → 결제하기. 결제창에 **아무 카드 정보**를 넣으면 승인되고 실제 출금은 없어요.
- 관리자 > 주문에서 `결제완료`, 상품 재고가 줄었는지 확인
- 주문 상세에서 `주문 취소` → 환불 + 재고 복구 확인
- 토스 개발자센터 > 테스트 결제내역에서도 확인 가능

## 10. (선택) 상품 이미지를 S3에 저장
**왜?** 이미지를 서버 디스크 대신 S3에 두면 서버를 바꾸거나 늘려도 이미지가 그대로 남아요.
**IAM 역할이란?** 0-2의 IAM 사용자가 '사람'에게 주는 계정이라면, IAM 역할은 'EC2 같은 AWS 서비스'에 주는 권한이에요. 역할을 EC2에 붙이면 서버에 액세스 키를 저장하지 않아도 S3를 쓸 수 있어서 키 유출 위험이 없어요.

1. **S3 버킷 만들기**(서울) → 퍼블릭 액세스 차단 해제 → 권한 → 버킷 정책에 아래 붙여넣기 (손님이 이미지를 볼 수 있게 `media/` 읽기만 허용)
   ```json
   {"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::버킷이름/media/*"}]}
   ```
2. **IAM 정책 만들기**: IAM → 정책 → 정책 생성 → JSON 탭에 아래 입력 → 이름 `ssingssing-s3-media` (이 버킷에만 올리기·읽기·지우기 허용)
   ```json
   {"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:PutObject","s3:GetObject","s3:DeleteObject"],"Resource":"arn:aws:s3:::버킷이름/media/*"}]}
   ```
3. **IAM 역할 만들기**: IAM → 역할 → 역할 생성 → 신뢰할 엔터티 **AWS 서비스 → EC2** → 방금 만든 정책 선택 → 이름 `ssingssing-ec2-role`
4. **EC2에 역할 연결**: EC2 → 인스턴스 선택 → 작업 → 보안 → **IAM 역할 수정** → `ssingssing-ec2-role`
5. `.env`에 `USE_S3=true`, `AWS_STORAGE_BUCKET_NAME=버킷이름` → `sudo systemctl restart ssingssing`
6. 이후 관리자에서 올리는 상품 이미지는 S3에 저장돼요. (이미 등록한 상품은 이미지를 다시 올려 주세요)

## 11. 운영 명령어
```bash
sudo journalctl -u ssingssing -f           # Django 로그 (결제 승인/취소 기록 포함)
sudo tail -f /var/log/nginx/error.log       # Nginx 에러
sudo systemctl restart ssingssing           # 코드·.env 수정 후 재시작
mysqldump -u shop -p ssingssing > backup_$(date +%F).sql   # DB 백업
```

## 막히면 먼저 볼 곳
- **502 Bad Gateway**: Django가 안 떠 있음 → `sudo journalctl -u ssingssing -n 50` (주로 .env 오타, DB 비밀번호)
- **400 Bad Request**: `.env`의 `ALLOWED_HOSTS`에 퍼블릭 IP가 없음
- **디자인 깨짐**: 8단계 `chmod 711` 누락 또는 collectstatic 누락
- **결제창 안 뜸**: 토스 키가 '결제위젯 연동 키'인지 확인 (API 개별 연동 키와 다름)
- **접속 자체가 안 됨**: 보안 그룹 80 포트, 주소를 `http://`로 입력했는지

---

## 실제 판매(실결제) 전에 꼭 필요한 것
1. **도메인 + HTTPS**: 결제·로그인은 반드시 HTTPS로 운영해야 해요. 도메인을 EC2 IP에 연결한 뒤
   `sudo dnf install -y certbot python3-certbot-nginx && sudo certbot --nginx -d 내도메인` → 보안 그룹 443 열기 → `.env`에 `USE_HTTPS=true`, 주소를 `https://내도메인`으로
2. **사업자등록 + 통신판매업 신고**
3. **토스페이먼츠 전자결제 계약·심사** → 라이브 키(`live_gck_`, `live_gsk_`)로 교체
4. **사이트 하단 사업자 정보, 이용약관, 개인정보처리방침** 게시
5. **DB 백업 자동화**, 트래픽이 늘면 DB를 RDS로 분리

## 다 쓰고 나서 정리 (요금 방지)
EC2 종료 → 탄력적 IP **릴리스**(연결만 끊으면 계속 과금) → S3 버킷 비우고 삭제 → EBS 볼륨·스냅샷 남았는지 확인
