# 保护期接口 — Payload / curl 模板

> 鉴权统一走 `cllmk curl`（Cookie），不要手写完整 curl。下面给出 cllmk 版本与 UI 完整 curl 对照，便于反推字段含义。

## 1. List — 查询全部规则

```bash
cllmk curl --url /api/outer/ats-jc/channel/protectionPeriod/list --method POST --payload '{}'
```

UI 原始 curl 关键点：
- 方法 POST，content-length 可为 0（空 body），cllmk 这边发 `{}` 等价
- referer 是 `/settings/protection_period_setting`，moka-tracing 里 `scenario:"social"`

返回结构：
```jsonc
{
  "code": 0,
  "data": {
    "code": 0,
    "data": [
      {
        "id": 100000103,          // 用于 changePriority
        "ruleId": 100000164,      // 内部规则引擎 id，不用
        "name": "马来西亚",
        "priority": 245,          // 数值越大越靠前
        "enabled": true,
        "lastModifyTime": 1782714604000,
        "lastModifyUserName": "<user-name>"
      }
      // ... 245+ 条
    ],
    "msg": "成功",
    "success": true
  }
}
```

---

## 2. Create — 新建一条国家维度规则

### Payload 结构

```jsonc
{
  "name": "<国家名 zh-CN>",
  "ruleConditionData": "<JSON 字符串>",   // 见下方 ruleConditionData 模板
  "content": {                             // 由用户提供，不要写死
    "headhunterLockInProcess": false,
    "rpoLockInProcess": false,
    "recommenderLockInProcess": false,
    "campusAmbassadorLockInProcess": false,
    "nonInterestChannelLockInProcess": false,
    "headhunterLockProtect": true,
    "headhunterProtectTime": 365,
    "rpoLockProtect": true,
    "rpoProtectTime": 365,
    "recommenderProtect": { "enabled": false, "time": null },
    "campusAmbassadorProtect": { "enabled": false, "time": null },
    "ownProtect": {
      "enabled": true,
      "time": -1,                    // -1 = 永久
      "headhunterTime": 365,
      "campusAmbassador": -1,
      "rpo": 365
    },
    "nonInductionTalentPoolLockProtect": false,
    "nonInductionTalentPoolLockProtectTime": null
  }
}
```

### ruleConditionData 模板（每条新规则需重新生成 3 个 UUID）

把这个对象 **JSON.stringify** 后作为 `ruleConditionData` 字段的字符串值：

```jsonc
{
  "orgId": "<当前租户 orgId>",       // 从 cllmk auth status 拿
  "bus": "ATS",
  "businessType": "protectionPeriod",
  "contextParam": { "buId": 0, "hireMode": 1 },
  "templateType": 1,
  "rule": {
    "uniqueKey": "<UUID1>",            // 每条都要重新生成
    "label": "ruleFamily",
    "rules": [{
      "uniqueKey": "<UUID2>",          // 重新生成
      "label": "ruleGroup",
      "logic": "and",
      "rules": [{
        "uniqueKey": "<UUID3>",        // 重新生成
        "label": "rule",
        "name": "【职位 / 国家/地区】 包含任意【<国家名>】 ",
        "features": [{
          "isCommon": true,
          "id": 100004000,
          "name": "job",
          "title": "职位 / 国家/地区",
          "type": 6,
          "featureConditions": [],
          "child": {
            "id": 100000034,
            "name": "countryRegion",
            "operators": ["IS_NULL","NOT_NULL","INCLUDE_ANY","NOT_INCLUDE_ANY"],
            "title": "国家/地区",
            "type": 6,
            "featureConditions": [],
            "child": null
          },
          "value": {
            "option": [{
              "id": 100000034,
              "name": "countryRegion",
              "operators": ["IS_NULL","NOT_NULL","INCLUDE_ANY","NOT_INCLUDE_ANY"],
              "title": "国家/地区",
              "type": 6,
              "value": "job.countryRegion",
              "label": "国家/地区",
              "defFeatureId": 100000034,
              "children": []
            }],
            "conditions": {}
          }
        }],
        "value": { "data": ["<国家名>"], "title": "<国家名>" },
        "operator": "INCLUDE_ANY"
      }]
    }]
  }
}
```

**关键替换点：**
- `orgId`：从 `cllmk auth status` 的 `data.orgId` 取
- `<国家名>` 出现 3 次：`rule.rules[0].rules[0].name`、`value.data[0]`、`value.title`
- 3 个 `uniqueKey` 全部用 `uuid4()` 新生成

### cllmk 调用

```bash
cllmk curl \
  --url /api/outer/ats-jc/channel/protectionPeriod/create \
  --method POST \
  --payload '<上述 JSON，整体作为字符串>'
```

返回成功示例：
```json
{"code":0,"data":{"code":0,"codeType":0,"data":true,"msg":"成功","success":true},"msg":""}
```

⚠️ **不返回新规则的 id**。要拿 id 必须再调一次 list。

---

## 3. changePriority — 调整优先级

```bash
cllmk curl \
  --url /api/outer/ats-jc/channel/protectionPeriod/changePriority \
  --method POST \
  --payload '{"id":<规则id>,"priority":<目标值>}'
```

### 行为参考表

设系统总规则数为 N（priority 区间 1..N）。规则当前 priority = `old_p`，发送 `priority = p_send`：

| 情况 | 规则最终 priority | 其他规则位移 |
|------|------------------|--------------|
| `p_send > old_p`（UP） | `p_send` | `[old_p+1, p_send]` 区间内 **-1** |
| `p_send < old_p`（DOWN） | `p_send + 1`（off-by-one） | `[p_send+1, old_p-1]` 区间内 **+1** |
| `p_send == old_p` | `old_p`（无变化） | 无 |

### 行为示例

**实例 A — UP 顶到 top：**
- 起始：国家 A 226，国家 B 246（top）
- 发送：`{"id":国家A的id, "priority": 246}`
- 结果：国家 A 246（top），国家 B → 245，[227, 246] 区间全部 -1

**实例 B — DOWN 移回原位：**
- 起始：国家 A 246（top），国家 B 227，国家 C 225
- 发送：`{"id":国家A的id, "priority": 226}`
- 结果：国家 A **227**（不是 226），国家 B 留在 226，[227, 245] 区间全部 +1

### "批量按指定顺序顶到 top K 位"算法

期望顺序 `[A1, A2, ..., AK]`（A1 在 #1，AK 在 #K）：

```python
for name in reversed([A1, A2, ..., AK]):
    changePriority(id=id_of(name), priority=N)   # N = 当前 max
```

最后调用的 A1 落到 priority N（= #1），A2 落到 #2，...，AK 落到 #K。

中间位置上原本就在那的规则会被挤到 K+1 之后。
