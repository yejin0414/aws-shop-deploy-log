"""기본 카테고리와 상품 8개를 등록합니다.  python manage.py seed_products"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from shop.models import Category, Product

SEED = [
    ("과일", "꿀사과 1.5kg", 15900, 12900, 50, "apple.png", "BEST", "아삭하고 달콤한 경북 청송 사과입니다."),
    ("과일", "제주 감귤 2kg", 13900, None, 40, "orange.png", "NEW", "새콤달콤한 제주 노지 감귤입니다."),
    ("과일", "샤인머스캣 1송이", 18900, 16900, 20, "grape.png", "", "씨 없이 껍질째 먹는 샤인머스캣입니다."),
    ("채소", "흙당근 1kg", 4900, None, 60, "carrot.png", "", "제주 구좌 흙당근, 주스용으로도 좋아요."),
    ("채소", "대추방울토마토 750g", 8900, 7900, 35, "tomato.png", "BEST", "한입에 쏙, 당도 높은 대추방울토마토입니다."),
    ("채소", "친환경 브로콜리 2입", 5900, None, 30, "broccoli.png", "", "농약 없이 키운 친환경 브로콜리입니다."),
    ("유제품·계란", "목장 우유 900ml", 3200, None, 80, "milk.png", "", "1등급 원유로 만든 신선한 우유입니다."),
    ("유제품·계란", "동물복지 유정란 15구", 9900, 8900, 25, "egg.png", "NEW", "넓은 농장에서 자란 닭이 낳은 유정란입니다."),
]


class Command(BaseCommand):
    help = "샘플 카테고리·상품을 등록합니다 (이미 있으면 건너뜀)."

    def handle(self, *args, **options):
        img_dir = Path(__file__).resolve().parents[2] / "seed_images"
        for i, name in enumerate(["과일", "채소", "유제품·계란"]):
            Category.objects.get_or_create(name=name, defaults={"order": i})

        created = 0
        for cat, name, price, sale, stock, img, badge, desc in SEED:
            if Product.objects.filter(name=name).exists():
                continue
            p = Product(category=Category.objects.get(name=cat), name=name, price=price, sale_price=sale,
                        stock=stock, badge=badge, description=desc)
            path = img_dir / img
            if path.exists():
                with path.open("rb") as f:
                    p.image.save(img, File(f), save=False)   # USE_S3=true 면 S3로 업로드됨
            p.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f"상품 {created}개를 등록했어요."))
