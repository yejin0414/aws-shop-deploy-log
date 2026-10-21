# AWS EC2 쇼핑몰 서버 구축 기록 (1일차)

신선식품 쇼핑몰 **싱싱마켓**(Django + MariaDB + 토스페이먼츠)을 AWS에 직접 배포하기 위해, 코드를 올리기 직전까지 서버를 구성한 과정입니다.
처음부터 끝까지 **휴대폰(AWS 콘솔 모바일 웹 + AWS Console 앱)**으로 진행했고, 중간에 막혔던 부분과 해결 과정도 함께 정리했습니다.

## 목표 구조

```
사용자 ──HTTP(80)──▶ [EC2: Amazon Linux 2023]
                      ├─ Nginx        (웹 서버, 정적 파일)
                      ├─ Gunicorn     (Django 실행)
                      ├─ Django       (쇼핑몰 백엔드)
                      └─ MariaDB      (회원·상품·주문 DB, 외부 비공개)
                             │
                             └─ 토스페이먼츠 API (결제 승인·취소)
```

## 진행 현황

- [x] IAM 사용자 생성 (그룹으로 권한 관리)
- [ ] IAM 정책·역할 (S3·CloudWatch용) — EC2에는 나중에 연결
- [x] EC2 인스턴스 생성 (t3.micro, 20GiB gp3, 서울 리전)
- [x] 보안 그룹 설정 (SSH 22, HTTP 80)
- [x] 탄력적 IP 할당·연결
- [x] EC2 Instance Connect로 접속
- [x] 패키지 설치 (Python 3.11, Nginx, MariaDB, unzip)
- [x] 스왑 2GB 설정
- [x] MariaDB 쇼핑몰 DB·계정 생성
- [ ] 코드 업로드 및 배포 (PC에서 진행 예정)

---

## 1. IAM 사용자 만들기

루트 계정은 결제 정보까지 모든 권한을 가진 계정이라, 평소 작업용으로 **IAM 사용자**를 따로 만들었습니다.

### 1-1. 사용자 생성 시작
IAM → IAM 사용자 → **사용자 생성**

<img src="images/01-iam-users.jpg" width="360">

### 1-2. 사용자 이름과 콘솔 암호
- **AWS Management Console에 대한 사용자 액세스 권한 제공**에 체크해야 콘솔 암호 항목이 나타남
- 콘솔 암호: **사용자 지정 암호** (8자 이상, 대문자·소문자·숫자·기호 중 3가지 이상)
- **다음 로그인 시 새 암호 생성** 체크 → 첫 로그인 때 비밀번호를 다시 정하게 함

<img src="images/02-iam-user-details.jpg" width="360">

### 1-3. 권한 설정: 그룹에 사용자 추가

<img src="images/03-iam-permission-options.jpg" width="360">

| 옵션 | 방식 |
|---|---|
| **그룹에 사용자 추가** ✅ | 권한을 그룹에 주고 사용자를 그룹에 넣음. 사용자가 늘어도 그룹만 관리하면 됨 (AWS 권장) |
| 권한 복사 | 기존 사용자의 권한을 그대로 복사 |
| 직접 정책 연결 | 사용자 한 명에게 정책을 바로 붙임 |

미리 만들어 둔 사용자 그룹을 선택했습니다.

<img src="images/04-iam-user-group.jpg" width="360">

### 1-4. 검토 및 생성
- 권한 요약에 `IAMUserChangePassword`(AWS 관리형)가 자동으로 붙음 → '다음 로그인 시 새 암호 생성'을 체크했기 때문에, 사용자가 자기 비밀번호를 바꿀 수 있도록 AWS가 추가
- 그룹 권한은 그룹을 통해 상속

<img src="images/05-iam-review.jpg" width="360">

### 1-5. 생성 완료
**콘솔 로그인 URL**(`https://<계정ID>.signin.aws.amazon.com/console`)은 IAM 사용자 전용 로그인 주소라 따로 저장했습니다. 암호는 이 화면에서만 확인·다운로드할 수 있습니다.

<img src="images/06-iam-user-created.jpg" width="360">

> 액세스 키는 만들지 않았습니다. 서버가 S3·CloudWatch를 쓸 때는 **IAM 역할**로 권한을 줄 예정입니다.

## 2. IAM 정책 (S3 + CloudWatch) — 준비

EC2 서버가 상품 이미지를 S3에 올리고, CloudWatch로 지표·로그를 보낼 수 있도록 **필요한 권한만** 담은 정책입니다. (최소 권한 원칙)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ShopImagesS3",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<버킷이름>/media/*"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": ["cloudwatch:PutMetricData", "ec2:DescribeVolumes", "ec2:DescribeTags"],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
        "logs:DescribeLogGroups", "logs:DescribeLogStreams", "logs:PutRetentionPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchAgentConfig",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:*:*:parameter/AmazonCloudWatch-*"
    }
  ]
}
```

| 묶음 | 하는 일 |
|---|---|
| ShopImagesS3 | 상품 이미지 올리기·읽기·지우기 (버킷의 `media/` 폴더로 범위 제한) |
| CloudWatchMetrics | 메모리·디스크 지표 전송 (CPU 외 지표는 에이전트 필요) |
| CloudWatchLogs | Nginx·Django 로그 전송 |
| CloudWatchAgentConfig | CloudWatch 에이전트 설정 불러오기 |

DB(MariaDB)는 같은 서버 안에서 비밀번호로 접속하고, 결제는 토스 키로 동작하기 때문에 AWS 권한이 따로 필요하지 않습니다.

## 3. EC2 인스턴스 만들기

### 3-1. 인스턴스 시작
EC2 → **인스턴스 시작** → 단계별 학습 없이 실행

<img src="images/07-ec2-launch-button.jpg" width="360">
<img src="images/08-ec2-getting-started.jpg" width="360">

### 3-2. 이름, AMI, 인스턴스 유형

<img src="images/09-ec2-name.jpg" width="360">
<img src="images/10-ec2-ami.jpg" width="360">
<img src="images/11-ec2-instance-type.jpg" width="360">

| 항목 | 설정 | 이유 |
|---|---|---|
| 리전 | 서울 (ap-northeast-2) | 한국 사용자 대상 |
| AMI | Amazon Linux 2023 (프리 티어) | AWS가 관리, 가볍고 Nginx·Gunicorn이 리눅스 기준 |
| 유형 | t3.micro (2 vCPU, 1GiB) | 프리 티어. Linux 요금이 Windows보다 저렴 |
| 개수 | 1 | 1대에 웹·앱·DB를 모두 올리는 구조, 프리 티어 750시간을 나눠 쓰지 않도록 |

### 3-3. 키 페어
서버 접속용 열쇠입니다. 서버에는 공개 키가 들어가고, 내려받은 `.pem` 파일(개인 키)로 로그인합니다. **다시 다운로드할 수 없어서** 안전한 곳에 보관했습니다.

- 유형: **RSA** / 형식: **.pem** (OpenSSH, Windows 10 이상·Mac 공용. `.ppk`는 PuTTY용)

<img src="images/12-ec2-create-key-pair.jpg" width="360">
<img src="images/13-ec2-key-pair-selected.jpg" width="360">

### 3-4. 네트워크 설정
- VPC: **기본 VPC** (`172.31.0.0/16`)
- 서브넷·가용 영역: 기본 설정 없음 (AWS가 선택)
- 퍼블릭 IP 자동 할당: **활성화** (인터넷에서 접속하기 위해 필요)

<img src="images/14-ec2-network-default.jpg" width="360">
<img src="images/15-ec2-network-edit.jpg" width="360">

### 3-5. 보안 그룹 (방화벽)
기본 이름(`launch-wizard-1`) 대신 용도를 알 수 있는 이름으로 새 보안 그룹을 만들었습니다.

<img src="images/16-ec2-sg-name-rule1.jpg" width="360">
<img src="images/17-ec2-sg-rule1-source.jpg" width="360">
<img src="images/18-ec2-sg-rule2-http.jpg" width="360">

| 규칙 | 유형 | 포트 | 소스 | 이유 |
|---|---|---|---|---|
| 1 | SSH | 22 | 0.0.0.0/0 (설정 기간 한정) | 휴대폰·PC IP가 달라 임시 개방, 이후 `내IP/32`로 축소 예정 |
| 2 | HTTP | 80 | 0.0.0.0/0 | 손님 IP를 알 수 없으므로 전체 허용 |
| - | MySQL | 3306 | **열지 않음** | DB는 서버 내부에서만 사용 |

> 콘솔이 "소스가 0.0.0.0/0인 규칙은 모든 IP에서 접근을 허용한다"고 경고합니다. SSH는 키 페어가 있어야 접속되지만, 작업이 끝나면 반드시 범위를 좁힐 계획입니다.
> `/24`(주소 256개), `/0`(모든 주소), `/32`(주소 1개)의 차이를 보안 그룹에 직접 적용해 봤습니다.

### 3-6. 스토리지와 파일 시스템
- 루트 볼륨: **20GiB gp3** (프리 티어 30GB 이내, 기본 3000 IOPS)
- 파일 시스템(S3 Files·EFS·FSx): **없음** — 서버 1대 구성이라 공유 파일 시스템이 필요 없음

<img src="images/19-ec2-storage.jpg" width="360">
<img src="images/20-ec2-file-system.jpg" width="360">

시작 후 추천 카드 중 **RDS 연결은 건너뜀** (DB를 EC2 안에 직접 설치하기로 결정). IAM 인스턴스 프로파일은 역할을 만든 뒤 `작업 → 보안 → IAM 역할 수정`으로 연결할 예정입니다.

## 4. 탄력적 IP 연결

자동 할당 퍼블릭 IP는 인스턴스를 중지했다 켜면 바뀌기 때문에, 고정 주소를 붙였습니다.

1. EC2 → 네트워크 및 보안 → 탄력적 IP → **탄력적 IP 주소 할당**
2. 작업 → **탄력적 IP 주소 연결** → 리소스 유형: 인스턴스, 프라이빗 IP: 기본 VPC 대역(`172.31.x.x`)의 내부 주소
3. 인스턴스 상세에서 퍼블릭 IP가 탄력적 IP로 바뀐 것 확인

> 할당만 하고 연결하지 않으면 과금되며, 삭제할 때는 연결 해제 후 **릴리스**까지 해야 합니다.

## 5. 서버 접속 (EC2 Instance Connect)

인스턴스 → 연결 → EC2 Instance Connect → **퍼블릭 IPv4 주소로 연결**, 사용자 `ec2-user`

```
   ,     #_
   ~\_  ####_        Amazon Linux 2023
  ~~  \_#####\
  ~~     \###|
  ~~       \#/ ___   https://aws.amazon.com/linux/amazon-linux-2023
   ~~       V~' '->
    ~~~         /
      ~~._.   _/
         _/ _/
       _/m/'
[ec2-user@ip-172-31-x-x ~]$
```

`.pem` 없이 브라우저에서 접속 가능 (AWS가 임시 키를 넣어 줌). `.pem`은 PC에서 scp로 코드를 올릴 때 사용합니다.

## 6. 패키지 설치 + 스왑

```bash
# 시스템 업데이트 + Python, Nginx, MariaDB, unzip
sudo dnf update -y && sudo dnf install -y python3.11 python3.11-pip nginx mariadb105-server unzip

# t3.micro는 메모리 1GB라 DB와 Django를 같이 돌리면 부족 → 스왑 2GB
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 && sudo chmod 600 /swapfile \
  && sudo mkswap /swapfile && sudo swapon /swapfile \
  && echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab

free -h   # Swap: 2.0Gi 확인
```

## 7. MariaDB 설정

```bash
sudo systemctl enable --now mariadb   # 지금 켜고, 재부팅 시 자동 시작
sudo mysql                            # root는 unix_socket 방식이라 비밀번호 없이 sudo로 접속
```

```sql
CREATE DATABASE ssingssing CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'shop'@'localhost' IDENTIFIED BY '<shop_비밀번호>';
GRANT ALL PRIVILEGES ON ssingssing.* TO 'shop'@'localhost';
FLUSH PRIVILEGES;
SHOW DATABASES;
```

| 계정 | 사용 주체 | 접속 방법 |
|---|---|---|
| root | 관리자(나) | `sudo mysql` (unix_socket) |
| shop | 쇼핑몰 프로그램 | `.env`의 `DB_PASSWORD`, `ssingssing` DB에만 권한 |

---

## 트러블슈팅

### ① IAM 사용자 생성 화면에 비밀번호 칸이 없음
- **원인**: "AWS Management Console에 대한 사용자 액세스 권한 제공 - 선택 사항"을 체크하지 않음
- **해결**: 체크 → 콘솔 암호 항목이 나타남
- **배운 점**: 콘솔 접근을 주지 않으면 로그인할 수 없는 계정이 만들어짐

### ② EC2 생성 시 IAM 인스턴스 프로파일 목록이 비어 있음
- **원인**: EC2용 IAM 역할을 아직 만들지 않음 (역할을 사용 사례 'EC2'로 만들어야 인스턴스 프로파일이 함께 생성됨)
- **해결**: 역할 없이 인스턴스를 먼저 생성하고, 나중에 `작업 → 보안 → IAM 역할 수정`으로 연결하기로 함
- **배운 점**: 정책 → 역할 → EC2 순서로 만들어야 하며, 역할은 실행 중인 인스턴스에도 나중에 붙일 수 있음

### ③ MariaDB root 접속 불가

DB 비밀번호를 바꾸려다 아래 오류가 연속으로 났습니다.

```console
[ec2-user@ip-172-31-x-x ~]$ ALTER USER 'root'@'localhost' IDENTIFIED BY '********';
-bash: ALTER: command not found
[ec2-user@ip-172-31-x-x ~]$ FLUSH PRIVILEGES;
-bash: FLUSH: command not found
[ec2-user@ip-172-31-x-x ~]$ sudo mysql
ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: NO)
```

두 가지 문제가 겹쳐 있었습니다.

| 증상 | 원인 |
|---|---|
| `-bash: ALTER: command not found` | DB 명령어(`ALTER`, `FLUSH`)를 리눅스 셸(`$`)에 입력함. DB 명령어는 `MariaDB [(none)]>` 프롬프트에서만 동작 |
| `ERROR 1045 (28000): Access denied ... (using password: NO)` | `mysql_secure_installation`에서 unix_socket 인증을 **n**으로 선택하고 root 비밀번호를 설정 → 이후 비밀번호 없이(`sudo mysql`) 접속 불가. 설정한 비밀번호도 기억나지 않음 |

이후 `mysql_secure_installation`을 다시 실행했지만, 기존 비밀번호가 남아 있어 현재 비밀번호 확인 단계에서 계속 틀렸다고 나왔습니다.

**해결**: DB에 데이터가 없는 상태라 데이터 디렉터리를 초기화하고 새로 만듦

```bash
sudo systemctl stop mariadb
sudo rm -rf /var/lib/mysql                                   # ⚠️ 빈 DB일 때만 사용
sudo mysql_install_db --user=mysql --datadir=/var/lib/mysql
sudo systemctl start mariadb
sudo mysql                                                   # 비밀번호 없이 접속 성공
```

```console
MariaDB [(none)]>
```

**배운 점**
- 프롬프트를 보고 지금 어디에 명령을 넣는지 구분하기: `[ec2-user@... ~]$` = 리눅스, `MariaDB [(none)]>` = DB
- root는 비밀번호보다 **unix_socket**(sudo 권한이 있어야 접속)이 관리도 쉽고 더 안전함
- 애플리케이션은 root가 아니라 **권한을 제한한 전용 계정(shop)**으로 DB에 접속
- `rm -rf /var/lib/mysql` 초기화는 데이터가 생긴 뒤에는 절대 쓰면 안 됨 → 앞으로는 `mysqldump` 백업 습관화

---

## 다음 할 일
- [ ] PC에서 `scp -i <키>.pem ssingssing.zip ec2-user@<탄력적IP>:~` 로 코드 업로드
- [ ] venv 생성, `requirements.txt` 설치, `.env` 작성
- [ ] `migrate`, `collectstatic`, 관리자 계정 생성
- [ ] Gunicorn(systemd) + Nginx 설정 → `http://<탄력적IP>` 접속 확인
- [ ] 토스페이먼츠 테스트 결제 → 승인·취소·재고 반영 확인
- [ ] IAM 역할 연결 → S3 이미지 저장, CloudWatch 에이전트 설치
- [ ] SSH 소스를 `내IP/32`로 축소, DB 비밀번호 강화
- [ ] 도메인 + HTTPS(Let's Encrypt)
