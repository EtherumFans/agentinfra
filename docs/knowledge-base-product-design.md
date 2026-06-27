# iCoDer 医学知识库 — 产品化设计

## 一、产品定位

### 一句话定位

面向医疗信息化系统的**中文临床编码知识库服务**，提供 ICD-10-CN 诊断、ICD-9-CM-3 手术、CHS-DRG 分组的标准化查询与映射能力。

### 目标用户

| 用户角色 | 场景 | 核心需求 |
|---------|------|---------|
| iCoDer 编码引擎 | 病历编码时查询候选编码 | 诊断名→编码、编码→层级、编码→DRG |
| 医院 HIS/EMR 系统 | 医生录入诊断时实时提示编码 | 模糊搜索、同义词匹配、层级展开 |
| 医保结算系统 | 上传结算清单前校验编码合规性 | 编码有效性、DRG 分组、支付标准 |
| 第三方医疗 AI 应用 | 调用编码能力作为基础设施 | REST API、SDK、批量查询 |
| 数据标注团队 | 构建医学数据集时需要标准编码 | 批量编码映射、导出 |

### 竞品对比

| 维度 | OMAHA 七巧板 | iCoDer 知识库 |
|------|-------------|-------------|
| 获取方式 | 付费会员制 | 开源/自部署 |
| 诊断编码 | 有 | 33K ICD-10-CN |
| 手术编码 | 有 | 23K ICD-9-CM-3 + DRG |
| DRG 分组 | 无 | 628 组 CHS-DRG 1.1, 99.2% 覆盖 |
| 支付标准 | 无 | 27 省市 |
| 术语关系 | 52 种属性关系 | 知识图谱 11 种关系 |
| 同义词 | 有 | OHDSI 5M 同义词 |
| 更新频率 | 季度 | 按需 |
| 部署方式 | SaaS (OMAHA 托管) | 自托管 (Docker) |

---

## 二、数据资产清单

### 核心数据

| 数据集 | 条目数 | 质量 | 优先级 |
|--------|--------|------|--------|
| ICD-10-CN 诊断 | 33,304 | 9/10 | P0 |
| ICD-9-CM-3 手术 (有名称) | 12,078 | 8/10 | P0 |
| ICD-9-CM-3 手术 (仅编码+DRG) | 11,087 | 6/10 | P1 |
| CHS-DRG 1.1 分组 | 628 DRG / 370 ADRG | 8/10 | P0 |
| 手术→DRG 映射 | 23,165 条 | 9/10 | P0 |
| 疾病目录层级 | 238 级 | 8/10 | P1 |
| 药品 ATC 编码 | 1,304 | 8/10 | P1 |

### 增强数据

| 数据集 | 条目数 | 优先级 |
|--------|--------|--------|
| 知识图谱关系 | 182,995 | P2 |
| OHDSI 同义词 | 5M (中文子集) | P2 |
| 临床指南知识 | 1,583 条 | P2 |
| 27 省市支付标准 | ~100 文件 | P1 |
| ICD-10 跨版本映射 | 医保版1.0↔2.0, 北京版↔国临版 | P2 |

---

## 三、数据模型

### 3.1 核心实体

```
                         ┌──────────────────┐
                         │   ICD10Chapter   │
                         │   (22 chapters)  │
                         └────────┬─────────┘
                                  │ 1:N
                         ┌────────▼─────────┐
                         │   ICD10Block     │
                         │   (code ranges)  │
                         └────────┬─────────┘
                                  │ 1:N
              ┌───────────────────┼───────────────────┐
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────┐ ┌─────────▼─────────┐
    │   ICD10Category   │ │ ICD9Chapter │ │    DRGVersion     │
    │   (3-digit)       │ │  (18 chs)   │ │ (1.0/1.1/2.0)    │
    └─────────┬─────────┘ └──────┬──────┘ └─────────┬─────────┘
              │                   │                   │
    ┌─────────▼─────────┐ ┌──────▼──────┐ ┌─────────▼─────────┐
    │ ICD10Subcategory  │ │  ICD9Code   │ │     ADRG         │
    │   (4-digit)       │ │ (23K codes) │ │   (370 groups)   │
    └─────────┬─────────┘ └──────┬──────┘ └─────────┬─────────┘
              │                   │                   │
    ┌─────────▼─────────┐        │          ┌────────▼─────────┐
    │   ICD10Code       │        │          │      DRG         │
    │   (33K codes)     │◄───────┘          │  (628 groups)    │
    │ name, hierarchy   │   mapped via      │ CC/MCC levels    │
    └───────────────────┘   ADRG lookup     └────────┬─────────┘
              │                                       │
              │                                       │
    ┌─────────▼─────────┐              ┌─────────────▼─────────┐
    │   CrossReference  │              │   PaymentStandard     │
    │ ICD10↔ICD9↔DRG   │              │ (27 provinces/cities) │
    └───────────────────┘              └───────────────────────┘
```

### 3.2 表结构

```sql
-- ICD-10 诊断编码
CREATE TABLE icd10_codes (
    id          TEXT PRIMARY KEY,        -- OMA7_D0000001
    code        TEXT NOT NULL,           -- A00.000
    name        TEXT NOT NULL,           -- 霍乱, 由于O1群霍乱弧菌...
    chapter     TEXT,                    -- 1
    chapter_name TEXT,                   -- 某些传染病和寄生虫病
    category    TEXT,                    -- A00
    subcategory TEXT,                    -- A00.0
    detail      TEXT,                    -- A00.000
    source      TEXT,                    -- OpenDRG_ICD10_医保版2.0
    parent_id   TEXT,                    -- FK → icd10_codes.id
    level       INTEGER,                -- 1=chapter, 2=block, 3=category, 4=sub, 5=detail
    is_active   BOOLEAN DEFAULT TRUE,
    UNIQUE(code)
);

-- ICD-9-CM-3 手术编码
CREATE TABLE icd9_codes (
    id              TEXT PRIMARY KEY,
    code            TEXT NOT NULL,       -- 37.5100
    name            TEXT,                -- 心脏移植术 (nullable for DRG grouping codes)
    chapter         TEXT,
    chapter_name    TEXT,
    category_code   TEXT,               -- 37
    category_name   TEXT,
    subcategory_code TEXT,              -- 37.5
    match_type      TEXT,               -- exact / fuzzy / none
    source          TEXT,
    parent_id       TEXT,
    level           INTEGER,
    UNIQUE(code)
);

-- DRG 版本
CREATE TABLE drg_versions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,           -- CHS-DRG 1.1
    year        INTEGER,                 -- 2023
    adrg_count  INTEGER,                 -- 370
    drg_count   INTEGER,                 -- 628
    is_current  BOOLEAN DEFAULT FALSE
);

-- ADRG 分组
CREATE TABLE adrg_groups (
    id          TEXT PRIMARY KEY,
    version_id  TEXT NOT NULL REFERENCES drg_versions(id),
    code        TEXT NOT NULL,           -- AA1
    name        TEXT,                    -- 心脏移植
    mdc_code    TEXT,                    -- MDCA
    mdc_name    TEXT                     -- 循环系统疾病及功能障碍
);

-- DRG 分组
CREATE TABLE drg_groups (
    id          TEXT PRIMARY KEY,
    version_id  TEXT NOT NULL,
    adrg_id     TEXT NOT NULL REFERENCES adrg_groups(id),
    code        TEXT NOT NULL,           -- AA19
    name        TEXT,                    -- 心脏移植伴极重度并发症
    cc_level    TEXT,                    -- 1=MCC, 2=CC, 3=无并发症
    is_active   BOOLEAN DEFAULT TRUE
);

-- 手术→DRG 映射
CREATE TABLE surgery_drg_mapping (
    id              TEXT PRIMARY KEY,
    icd9_code       TEXT NOT NULL REFERENCES icd9_codes(code),
    drg_group_id    TEXT NOT NULL REFERENCES drg_groups(id),
    adrg_group_id   TEXT REFERENCES adrg_groups(id),
    mdc_code        TEXT,
    UNIQUE(icd9_code, drg_group_id)
);

-- 诊断→DRG 映射
CREATE TABLE diagnosis_drg_mapping (
    id              TEXT PRIMARY KEY,
    icd10_code      TEXT NOT NULL REFERENCES icd10_codes(code),
    drg_group_id    TEXT NOT NULL REFERENCES drg_groups(id),
    mdc_code        TEXT
);

-- 支付标准
CREATE TABLE payment_standards (
    id          TEXT PRIMARY KEY,
    region      TEXT NOT NULL,           -- 北京 / 上海 / 浙江...
    year        INTEGER,                 -- 2022
    drg_code    TEXT NOT NULL,           -- AA19
    drg_name    TEXT,
    price       DECIMAL(12,2),           -- 支付金额
    weight      DECIMAL(8,4),            -- 权重
    source_file TEXT
);

-- 跨编码映射
CREATE TABLE cross_references (
    id              TEXT PRIMARY KEY,
    source_system   TEXT,                -- ICD-10-CN / ICD-9-CM-3 / SNOMED / LOINC
    source_code     TEXT,
    target_system   TEXT,
    target_code     TEXT,
    mapping_type    TEXT,                -- ExactMatch / BroadMatch / NarrowMatch
    confidence      REAL                 -- 0.0-1.0
);
```

---

## 四、API 设计

### 基础路径: `/api/kb/v1`

### 4.1 诊断编码

```
GET  /icd10/search?q=糖尿病&limit=20&offset=0
     → { results: [{code, name, chapter, hierarchy}], total: N }

GET  /icd10/{code}
     → { code, name, chapter, chapter_name, category, subcategory,
         parent: {code, name}, children: [{code, name}],
         drg_mappings: [{mdc, adrg_code, drg_code}],
         synonyms: [] }

GET  /icd10/chapters
     → [{chapter, chapter_name, code_count}]

GET  /icd10/hierarchy?root=A00
     → tree structure of all codes under A00
```

### 4.2 手术编码

```
GET  /icd9/search?q=心脏移植&limit=20
GET  /icd9/{code}
GET  /icd9/chapters
```

### 4.3 DRG 分组

```
POST /drg/group
     Body: { diagnosis_codes: ["I21.100", "I10.x02"],
             procedure_code: "00.6600x002",
             version: "chs_1.1" }
     → { mdc: "MDCF", adrg: "FM1", drg: "FM19",
         drg_name: "经皮冠状动脉支架植入",
         cc_level: "伴极重度并发症",
         payment: { beijing: 45000, shanghai: 52000 } }

GET  /drg/adrg?version=chs_1.1
GET  /drg/{drg_code}?version=chs_1.1
```

### 4.4 支付标准

```
GET  /payment/standards?region=北京&year=2022&drg=AA19
GET  /payment/regions
```

### 4.5 批量 / 工具

```
POST /batch/search      # 批量编码查询 (最多 100 个)
POST /batch/drg         # 批量 DRG 分组 (最多 50 个)
GET  /export/icd10      # 导出 ICD-10 全量 (CSV/JSON)
GET  /export/icd9       # 导出 ICD-9 全量
GET  /health            # 服务健康检查
GET  /stats             # 知识库统计信息
```

### 4.6 响应格式

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "version": "CHS-DRG-1.0+1.1",
    "source": "OpenDRG + 医保版2.0",
    "updated_at": "2026-04-08"
  }
}
```

---

## 五、技术架构

```
┌─────────────────────────────────────────────┐
│                 API Layer                    │
│  FastAPI (:8100) + Swagger + Rate Limit     │
├─────────────────────────────────────────────┤
│              Service Layer                   │
│  SearchService  GroupingService  ExportSvc   │
├─────────────────────────────────────────────┤
│              Data Layer                      │
│  SQLite (dev) / PostgreSQL (prod)            │
│  + FAISS vector index (semantic search)     │
├─────────────────────────────────────────────┤
│              Data Pipeline                   │
│  Import scripts (one-time)                   │
│  + /admin/reload (hot-reload data)           │
└─────────────────────────────────────────────┘
```

### 部署 (本地开发 Docker, 生产走托管云 SaaS)

```yaml
# docker-compose.local-dev.yml   # 本地开发专用
services:
  kb-api:
    build: ./knowledge-base
    ports: ["8100:8100"]
    volumes:
      - ./data:/app/data
    environment:
      - KB_DB_PATH=/app/data/kb.db
      - KB_LOG_LEVEL=INFO
      - ICODER_DEPLOYMENT_MODE=local   # 2026-06-27 cloud-flip: 默认 local
```

> **2026-06-27 cloud-flip**: v1 不再医院内网 Docker 部署, knowledge-base 子服务托管云内嵌为受管服务 (per-tenant region 路由)。本地 Docker 仅作开发用途。详见 [docs/cloud/CLOUD_DEPLOYMENT.md](../cloud/CLOUD_DEPLOYMENT.md)。

### 目录结构

```
knowledge-base/
├── app/
│   ├── main.py              # FastAPI entry
│   ├── config.py            # Settings
│   ├── database.py          # DB connection
│   ├── models/
│   │   ├── icd10.py
│   │   ├── icd9.py
│   │   └── drg.py
│   ├── api/
│   │   ├── icd10.py         # GET /icd10/*
│   │   ├── icd9.py          # GET /icd9/*
│   │   ├── drg.py           # POST /drg/group
│   │   ├── payment.py       # GET /payment/*
│   │   ├── batch.py         # POST /batch/*
│   │   └── admin.py         # GET /admin/*
│   ├── services/
│   │   ├── search.py        # Full-text search
│   │   ├── grouper.py       # DRG grouping logic
│   │   ├── hierarchy.py     # Tree traversal
│   │   └── export.py        # Data export
│   └── pipeline/
│       ├── import_icd10.py  # ICD-10 ETL
│       ├── import_icd9.py   # ICD-9 ETL
│       └── import_drg.py    # DRG ETL
├── data/
│   ├── kb.db                # SQLite database (auto-created)
│   └── sources/             # Source data symlinks
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 六、iCoDer 集成方式

iCoDer 通过 HTTP 调用知识库服务，替换当前的硬编码查找：

```python
# 之前: 直接查本地字典
from app.services.code_dictionary import code_dict_service
result = code_dict_service.search_icd10("糖尿病")

# 之后: 调用知识库 API
import httpx
async with httpx.AsyncClient() as client:
    resp = await client.get(
        "http://localhost:8100/api/kb/v1/icd10/search",
        params={"q": "糖尿病", "limit": 20}
    )
    result = resp.json()["data"]
```

iCoDer 的 `code_dictionary.py` 改为适配器模式：
- 如果 `KB_API_URL` 配置了，调用远程 API
- 否则回退到本地字典（用于离线/开发环境）

---

## 七、运营设计

### 版本管理

```
/kb/v1  → 当前版本 (CHS-DRG 1.1)
/kb/v2  → 未来版本 (CHS-DRG 2.0)
```

API 路径包含版本号，老版本不下线，新版本独立部署。

### 数据更新流程

```
1. 准备新数据 (如 CHS-DRG 2.0 更新)
2. 运行导入脚本 → 生成 kb_v2.db
3. 部署新容器 (kb-v2:8101)
4. 灰度切换: iCoDer 配置 KB_API_URL 指向 v2
5. 验证无误后下线 v1
```

### 监控指标

- 搜索延迟 (P50/P95/P99)
- DRG 分组延迟
- 错误率
- 热门搜索词 Top 20
- 各端点 QPS

---

## 八、开发计划

| 阶段 | 内容 | 时间 |
|------|------|------|
| Phase 1: MVP | ICD-10 搜索 + ICD-9 搜索 + 健康检查 | 2 天 |
| Phase 2: DRG | DRG 分组 + ADRG 查询 + 映射 | 1 天 |
| Phase 3: 支付 | 支付标准查询 + 批量接口 | 1 天 |
| Phase 4: 增强 | 同义词搜索 + 层级遍历 + 导出 | 1 天 |
| Phase 5: 集成 | iCoDer 适配器 + 文档 + 部署 | 1 天 |
| **合计** | | **6 天** |
