# 通达信MCP使用说明

> 编写日期：2026-06-14 | 数据来源：通达信后台接口

---

## 工具全景（11个工具，分四层）

### 第一层：实时行情（最快，毫秒级）

| 工具 | 接口说明 | 典型用时 |
|------|------|:--:|
| **tdx_quotes** | 实时行情：现价/涨跌/开盘/最高最低/成交额/换手率/PE/PB/总市值/流通市值/盘口5档/主力净流入/年涨停天数 | ~200ms |
| **tdx_kline** | K线数据：日线/周线/月线/分钟线，支持前复权/后复权/不复权 | ~300ms |
| **tdx_lookup_stock** | 模糊查代码：输入名称/简称/拼音→返回精确代码+setcode | ~150ms |

### 第二层：选股筛选（较快，秒级）

| 工具 | 接口说明 | 典型用时 |
|------|------|:--:|
| **tdx_screener** | 条件选股：自然语言描述→返回符合条件的股票列表。涨停/跌停/炸板/连板/主力流入/放量/金叉… | 2-6s |
| **tdx_indicator_select** | 多指标对比：同时查多只股票的PE/PB/ROE/营收增速/主营构成等，横向对比 | 2-3s |

### 第三层：资讯查询（中等，秒级）

| 工具 | 接口说明 | 典型用时 |
|------|------|:--:|
| **wenda_news_query** | 新闻资讯：按关键词+时间范围搜A股/行业新闻 | 1-2s |
| **wenda_notice_query** | 公告查询：搜公司公告/临时公告/定期报告 | 1-2s |
| **wenda_report_query** | 研报查询：券商研报/评级/目标价 | 1-2s |
| **wenda_macro_query** | 宏观数据：CPI/PPI/社融/GDP/利率 | 1-2s |

### 第四层：深度数据（tdx_api_data，80+接口）

| 工具 | 接口说明 | 典型用时 |
|------|------|:--:|
| **tdx_api_data** | 统一API入口，内含80+个entry，覆盖F10全部深度数据 | 200ms-3s |

---

## tdx_api_data 完整接口列表

### 一、公司基本面（7个）

| entry | tag | 拉什么 |
|------|------|------|
| `tdxf10_gg_zxts` | gsgy | 公司概要：主营、地位、关联概念 |
| `tdxf10_gg_gsgk` | 0 | 基本信息：注册资本、法人、成立日期 |
| `tdxf10_gg_gsgk` | 8 | 发行交易：IPO价、发行量、保荐机构 |
| `tdxf10_gg_gsgk` | 20 | 董监高：高管名单、简历、薪酬 |
| `tdxf10_gg_gsgk` | 3 | 参控股公司：子公司、持股比例 |
| `tdxf10_gg_gsgk` | 4 | 员工构成：人数、学历、岗位结构 |
| `tdxf10_gg_gsgk` | 5 | 员工效益：人均创收、人均薪酬 |

### 二、财务三表+指标（10个）

| entry | tag | 拉什么 |
|------|------|------|
| `ph_agf10_cw_lyb` | 00101 | 利润表（年度/报告期） |
| `ph_agf10_cw_lyb` | 00102 | 利润表（单季度） |
| `ph_agf10_cw_xjllb` | 00101 | 现金流量表（报告期） |
| `ph_agf10_cw_xjllb` | 00102 | 现金流量表（单季度） |
| `ph_agf10_cw_zcfzb` | — | 资产负债表 |
| `ph_agf10_jyfx` | 00202 | 主营构成（分产品/分地区） |
| `ph_agf10_gzfx` | — | 估值历史走势 |
| `ph_agf10_hypm` | 00102 | 行业财务排名 |
| `ph_agf10_hypm` | 00105 | 行业估值排名 |
| `tdxf9_ag_cwsj_yjyj` | — | 业绩预警（预告类型/净利润变动） |

### 三、股本股东（14个）

| entry | tag | 拉什么 |
|------|------|------|
| `tdxf10_gg_gbjg` | gbjg | 股本结构（流通/限售） |
| `tdxf10_gg_gbjg` | gbbd | 股本变动历史 |
| `tdxf10_gg_gbjg` | xslt | 限售解禁时间表 |
| `tdxf10_gg_gbjg` | gphg | 股票回购记录 |
| `tdxf10_gg_gdyj` | gdrs | 股东人数变化趋势 |
| `tdxf10_gg_gdyj` | thygdrs | 股东人数行业排名 |
| `tdxf10_gg_gdyj` | sdgdbgq | 十大股东（报告期维度） |
| `tdxf10_gg_gdyj` | ltgd | 十大流通股东 |
| `tdxf10_gg_gdyj` | jgcg | 机构持股汇总 |
| `tdxf10_gg_gdyj` | kggd | 控股股东与实控人 |
| `tdxf10_gg_gdyj` | cgbd | 股东增减持明细 |
| `tdxf10_gg_gdyj_jgcgmx` | — | 机构持股明细（分基金/券商/保险） |
| `tdxf10_gg_gdyjcgmx` | gdjc | 股东进出详情 |
| `ph_agf10_gbgd_jgcc` | — | 机构持仓变化 vs 股价走势对比 |

### 四、交易数据（8个）

| entry | tag | 拉什么 |
|------|------|------|
| `tdxf10_gg_jyds` | jglhb | 龙虎榜明细（买入/卖出前5席位） |
| `tdxf10_gg_jyds` | dzjy | 大宗交易明细 |
| `tdxf10_gg_jyds` | rzrq | 融资融券余额变化 |
| `tdxf10_gg_jyds` | zjlx | 资金流向（主力/超大单/大单净额） |
| `tdxf10_gg_jyds` | ztfx | **涨停分析**（历史每次涨停的原因+主题） |
| `tdxf10_gg_jyds` | dtfx | 跌停分析 |
| `tdxf10_gg_zlcc` | bszj | 北向资金持仓变化 |
| `tdxf10_gg_iyds` | yxsbxx | 大宗交易意向申报 |

### 五、分红融资（12个）

| entry | tag | 拉什么 |
|------|------|------|
| `tdxf10_gg_fhrz` | pxmz | 分红与募资概览 |
| `tdxf10_gg_fhrz` | fh | 分红历史走势图 |
| `tdxf10_gg_fhrz` | zf | 增发方案与实施 |
| `tdxf10_gg_fhrz` | pf | 配股方案 |
| `tdxf10_gg_fhrz` | zfpg | 增发获配明细 |
| `tdxf10_gg_fhrz` | fhlszs_gxl | 股息率历史走势 |
| `tdxf10_gg_fhrz` | fhlszs_glzfl | 股利支付率历史走势 |
| `tdxf10_gg_fhrz` | fhpm_gxl | 股息率全市场排名 |
| `tdxf10_gg_fhrz` | fhpm_glzfl | 股利支付率排名 |
| `tdxf10_gg_fhrz` | fhpm_pxrzb | 派现融资比排名 |
| `tdxf10_gg_fhrz_fh` | fh | 分红表（每次分红明细） |
| `tdxf10_gg_sj` | fh_sj | 分红视界（多股对比） |

### 六、热点题材（4个）

| entry | tag | 拉什么 |
|------|------|------|
| `tdxf10_gg_rdtc` | zttzbkz | 板块族谱（该股属于哪些概念板块） |
| `tdxf10_gg_rdtc` | zttzztk | 主题库（市场热点主题分类） |
| `tdxf10_gg_rdtc` | sjcd | 事件驱动（近期催化事件与股价联动） |
| `tdxf10_gg_rdtc` | xxmmg | 信息面概览（综合消息面分析） |

### 七、行业/板块/产业链（7个）

| entry | branch | 拉什么 |
|------|------|------|
| `cfg_tk_gethy` | — | 行业产业链（上游→中游→下游全链条） |
| `skef10_hy_zxdt_hyzysj` | — | 行业重要事件 |
| `skef10_bk_cpbd_jczl` | 001 | 板块基础资料 |
| `skef10_bk_cpbd_jczl` | 002 | 板块详解 |
| `skef10_bk_cpbd_jczl` | 003 | 板块阶段涨幅 |
| `skef10_bk_cpbd_jczl` | 004 | 板块市场统计 |
| `skef10_hy_hydw_gzsppm` | — | 板块估值对比 |

### 八、研报数据（1个）

| entry | tag | 拉什么 |
|------|------|------|
| `tdxf10_gg_ybpj` | yzyq | 研报评级一致预期（目标价/评级分布） |

---

## 速度分级

| 级别 | 用时 | 工具 | 说明 |
|:--:|------|------|------|
| ⚡极快 | 100-300ms | tdx_quotes / tdx_lookup_stock / tdx_api_data大部分 | 单只查询，直接命中 |
| 🟢快 | 1-3s | tdx_kline / wenda_* / tdx_indicator_select | 需要后端组装数据 |
| 🟡中等 | 2-6s | tdx_screener | 全市场扫描+条件筛选 |
| 🔴逐只查慢 | N×300ms | tdx_api_data 逐只查连板原因 | 20只连板=20次调用=约6秒 |

---

## 调用示例

```bash
# 实时行情
tdx_quotes code="600519" setcode="1"

# K线（日线，前复权，最近100根）
tdx_kline code="600519" setcode="1" period="4"

# 条件选股
tdx_screener message="涨停" rang="AG" pageSize="20"

# 公司概要
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_zxts" fixedTag="gsgy" code="000547"

# 涨停分析
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_jyds" fixedTag="ztfx" code="600367" extra="2026-06-12"

# 利润表
tdx_api_data entry="TdxShareCW.ph_agf10_cw_lyb" fixedTag="00101" code="600519"

# 股东人数
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gdyj" fixedTag="gdrs" code="300750" pageNo="1" pageSize="20"

# 行业产业链
tdx_api_data entry="TdxSharePCCW.cfg_tk_gethy" industryCode="..."
```

---

## 数据来源说明

**所有数据均为通达信后台直接返回，不做二次加工：**

| 数据类型 | 来源 |
|------|------|
| 涨停原因+主题 | 通达信F10内置，分析师后台标注 |
| 资金流向 | 通达信L2数据引擎计算 |
| 龙虎榜 | 交易所原始数据，通达信格式化 |
| 财务三表 | 公司公告→通达信数据库结构化 |
| 机构持仓 | 季报/年报→通达信聚合 |
| 产业链映射 | 通达信行业研究团队维护 |
| 研报评级 | 各券商研报→通达信聚合 |
