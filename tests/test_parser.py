"""Tests for parser module."""
from src.models import Customer
from src.parser import parse_customers


def test_parse_sample_customers():
    path = "examples/sample_customers.xlsx"
    aliases = {
        "id": ["客户序号", "ID", "id", "customer_id"],
        "name": ["客户名", "公司名称", "customer_name", "company_name", "name"],
        "business_positioning": ["客户商业定位", "商业定位", "business_positioning"],
        "region_positioning": ["客户区域定位", "区域定位", "region_positioning"],
        "main_products": ["主营商品", "产品", "main_products", "products"],
        "hs_codes": ["HS CODE", "HS编码", "海关编码", "hs_code", "hs_codes"],
        "annual_shipment_frequency": ["年发货频次", "发货频次", "annual_shipment_frequency"],
        "annual_china_purchase": ["年中国采购额度", "中国采购额", "annual_china_purchase"],
        "customer_revenue": ["客户营业额", "营业额", "customer_revenue"],
    }
    customers = parse_customers(path, aliases)
    assert len(customers) == 16
    assert all(isinstance(c.hs_codes, list) for c in customers)
    assert all(c.id for c in customers)
