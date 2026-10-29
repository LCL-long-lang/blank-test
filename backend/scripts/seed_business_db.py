"""生成电商示例业务库 data/business.db。

固定随机种子，结果可复现；数据带季节性（春节、618、双 11）和区域差异，便于画趋势与对比图。
用法：python scripts/seed_business_db.py [--orders 20000] [--months 24]
"""
import argparse
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402

SEED = 20261004

REGIONS = {
    "华东": ["上海", "江苏", "浙江", "安徽", "福建", "山东"],
    "华南": ["广东", "广西", "海南"],
    "华北": ["北京", "天津", "河北", "山西", "内蒙古"],
    "华中": ["河南", "湖北", "湖南", "江西"],
    "西南": ["重庆", "四川", "贵州", "云南"],
    "西北": ["陕西", "甘肃", "宁夏", "新疆"],
    "东北": ["辽宁", "吉林", "黑龙江"],
}
# 各大区下单权重（体现区域差异）
REGION_WEIGHT = {"华东": 30, "华南": 20, "华北": 18, "华中": 12, "西南": 10, "西北": 5, "东北": 5}

# 品类：(名称, 品牌列表, 价格区间, 毛利率区间)
CATEGORIES = [
    ("手机数码", ["华为", "小米", "苹果", "OPPO", "vivo"], (999, 8999), (0.08, 0.20)),
    ("家用电器", ["美的", "格力", "海尔", "戴森"], (299, 6999), (0.12, 0.28)),
    ("服装鞋包", ["优衣库", "李宁", "安踏", "耐克"], (59, 899), (0.35, 0.60)),
    ("美妆个护", ["欧莱雅", "雅诗兰黛", "珀莱雅", "兰蔻"], (49, 1299), (0.45, 0.70)),
    ("食品饮料", ["三只松鼠", "伊利", "蒙牛", "良品铺子"], (9, 199), (0.20, 0.40)),
    ("图书文娱", ["中信出版", "人民文学", "机械工业"], (19, 159), (0.25, 0.45)),
    ("家居日用", ["宜家", "无印良品", "网易严选"], (19, 999), (0.30, 0.55)),
    ("运动户外", ["迪卡侬", "探路者", "北面"], (49, 2999), (0.30, 0.50)),
]
PRODUCT_SUFFIX = ["标准版", "Pro", "Max", "青春版", "旗舰款", "经典款", "Plus", "限定款"]

SURNAMES = "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾"
GIVEN = "伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英华建国玉兰"
MEMBER_LEVELS = [("普通", 60), ("银卡", 25), ("金卡", 11), ("钻石", 4)]
PAYMENTS = [("支付宝", 45), ("微信支付", 40), ("银行卡", 10), ("货到付款", 5)]
STATUSES = [("completed", 88), ("cancelled", 7), ("refunded", 5)]

DDL = """
CREATE TABLE regions (
    region_id   INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL,
    province    TEXT NOT NULL
);
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    gender        TEXT NOT NULL,
    age           INTEGER NOT NULL,
    city          TEXT NOT NULL,
    region_id     INTEGER NOT NULL REFERENCES regions(region_id),
    register_date TEXT NOT NULL,
    member_level  TEXT NOT NULL
);
CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL
);
CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category_id  INTEGER NOT NULL REFERENCES categories(category_id),
    brand        TEXT NOT NULL,
    unit_price   REAL NOT NULL,
    cost_price   REAL NOT NULL
);
CREATE TABLE orders (
    order_id       INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date     TEXT NOT NULL,
    status         TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    total_amount   REAL NOT NULL
);
CREATE TABLE order_items (
    item_id    INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
"""



def weighted(rng: random.Random, pairs: list[tuple[str, int]]) -> str:
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]


def months_back(end: date, n_months: int) -> date:
    """包含 end 所在月在内，往前 n_months 个月的第一天。"""
    idx = end.year * 12 + (end.month - 1) - (n_months - 1)
    return date(idx // 12, idx % 12 + 1, 1)


def day_weight(d: date, start: date, total_days: int) -> float:
    """某天的下单热度：整体增长趋势 × 月度季节性 × 大促/节假日。"""
    trend = 1.0 + 0.5 * (d - start).days / max(total_days, 1)       # 两年增长约 50%
    month_factor = {1: 0.9, 2: 0.75, 3: 0.95, 4: 0.95, 5: 1.0, 6: 1.25,
                    7: 0.95, 8: 0.95, 9: 1.0, 10: 1.05, 11: 1.45, 12: 1.2}[d.month]
    promo = 1.0
    if d.month == 6 and 1 <= d.day <= 18:
        promo = 1.8 if d.day == 18 else 1.3                           # 618
    elif d.month == 11 and 1 <= d.day <= 11:
        promo = 3.5 if d.day == 11 else 1.4                           # 双 11
    elif d.month == 12 and d.day == 12:
        promo = 1.8                                                   # 双 12
    weekend = 1.15 if d.weekday() >= 5 else 1.0
    return trend * month_factor * promo * weekend


def build(db_path: Path, n_orders: int, n_months: int, end: date) -> dict[str, int]:
    rng = random.Random(SEED)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)

    # 地区
    regions, region_ids = [], {}
    for rname, provinces in REGIONS.items():
        for prov in provinces:
            rid = len(regions) + 1
            regions.append((rid, rname, prov))
            region_ids.setdefault(rname, []).append(rid)
    conn.executemany("INSERT INTO regions VALUES (?,?,?)", regions)

    # 品类与商品
    conn.executemany("INSERT INTO categories VALUES (?,?)",
                     [(i + 1, c[0]) for i, c in enumerate(CATEGORIES)])
    products = []
    for cid, (_, brands, (lo, hi), (m_lo, m_hi)) in enumerate(CATEGORIES, start=1):
        for _ in range(25):
            brand = rng.choice(brands)
            price = round(rng.uniform(lo, hi) / 10) * 10 - 1 if hi > 200 else round(rng.uniform(lo, hi), 1)
            price = max(price, lo)
            cost = round(price * (1 - rng.uniform(m_lo, m_hi)), 2)
            name = f"{brand} {CATEGORIES[cid - 1][0][:2]}{rng.randint(1, 99)} {rng.choice(PRODUCT_SUFFIX)}"
            products.append((len(products) + 1, name, cid, brand, float(price), cost))
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", products)

    # 客户
    start = months_back(end, n_months)
    total_days = (end - start).days + 1
    customers = []
    region_names = list(REGION_WEIGHT)
    for cid in range(1, 2001):
        rname = rng.choices(region_names, weights=list(REGION_WEIGHT.values()))[0]
        rid = rng.choice(region_ids[rname])
        province = regions[rid - 1][2]
        name = rng.choice(SURNAMES) + "".join(rng.choices(GIVEN, k=rng.choice([1, 2])))
        reg = start - timedelta(days=365) + timedelta(days=rng.randint(0, total_days + 300))
        reg = min(reg, end)
        customers.append((cid, name, rng.choice(["男", "女"]), rng.randint(18, 65),
                          province, rid, reg.isoformat(), weighted(rng, MEMBER_LEVELS)))
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", customers)

    # 订单：按每日热度分配订单量
    days = [start + timedelta(days=i) for i in range(total_days)]
    order_days = rng.choices(days, weights=[day_weight(d, start, total_days) for d in days], k=n_orders)
    order_days.sort()
    # 会员等级越高越活跃（复购更多）
    level_boost = {"普通": 1, "银卡": 2, "金卡": 3.5, "钻石": 6}
    cust_weights = [level_boost[c[7]] for c in customers]
    # 大区品类偏好：让不同区域的品类结构有差异
    region_pref = {r: [rng.uniform(0.6, 1.6) for _ in CATEGORIES] for r in REGIONS}
    by_cat: dict[int, list[tuple]] = {}
    for p in products:
        by_cat.setdefault(p[2], []).append(p)

    orders, items = [], []
    for oid, d in enumerate(order_days, start=1):
        cust = rng.choices(customers, weights=cust_weights)[0]
        rname = regions[cust[5] - 1][1]
        ts = datetime(d.year, d.month, d.day, rng.choices(range(24), weights=[1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 7, 6, 6, 6, 6, 6, 7, 9, 10, 10, 8, 4])[0],
                      rng.randint(0, 59), rng.randint(0, 59))
        total = 0.0
        for _ in range(rng.choices([1, 2, 3, 4], weights=[50, 30, 14, 6])[0]):
            cat = rng.choices(range(1, len(CATEGORIES) + 1), weights=region_pref[rname])[0]
            p = rng.choice(by_cat[cat])
            qty = rng.choices([1, 2, 3, 5], weights=[70, 20, 7, 3])[0]
            # 大促期间有折扣
            discount = 0.85 if (d.month, d.day) in {(6, 18), (11, 11), (12, 12)} else 1.0
            price = round(p[4] * discount, 2)
            items.append((len(items) + 1, oid, p[0], qty, price))
            total += qty * price
        orders.append((oid, cust[0], ts.strftime("%Y-%m-%d %H:%M:%S"), weighted(rng, STATUSES),
                       weighted(rng, PAYMENTS), round(total, 2)))
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)", items)
    conn.commit()

    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["regions", "customers", "categories", "products", "orders", "order_items"]}
    span = conn.execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    conn.close()
    counts["_span"] = f"{span[0][:10]} ~ {span[1][:10]}"
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="生成电商示例业务库")
    parser.add_argument("--orders", type=int, default=20000)
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today() - timedelta(days=1),
                        help="数据截止日期，默认昨天（让“近 N 个月”类问题有数据）")
    parser.add_argument("--out", type=Path, default=settings.business_db_path)
    args = parser.parse_args()

    counts = build(args.out, args.orders, args.months, args.end_date)
    print(f"已生成 {args.out}")
    print(f"订单时间范围：{counts.pop('_span')}")
    for table, n in counts.items():
        print(f"  {table:<12} {n:>7} 行")


if __name__ == "__main__":
    main()
