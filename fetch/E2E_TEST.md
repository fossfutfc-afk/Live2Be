# Live2Be IDE Agent 端到端测试报告

- 日期: 2026-08-17T19:25:43
- LLM: `deepseek-v4-flash` @ `https://api.deepseek.com/v1`
- 隔离工作目录: `C:\Users\johnf\AppData\Local\Temp\live2be_e2e_mg7w8bid`（不污染真实 config）

## 任务 1：创建原创角色 (OC)

**用户输入**: 帮我创建一个原创角色(OC)，角色 id 用 'my_oc_test'，显示名叫'测试酱'，性格胆小但内心善良。这是用户自己构思的角色，不需要查网页资料，直接创建。

### 步骤 0 · LLM 动作

- 契约解析: ❌ 无效
- 错误: ['basis 必须是列表', 'profile.yml 必须是非空 YAML 文本']
- 警告: ['该动作缺少 sources；宁缺勿错，请勿编造依据']

### 步骤 1 · LLM 动作

- 动作: **create_character**  (审批: `required`)
- summary: 正在创建原创角色『测试酱』（id: my_oc_test），性格胆小但内心善良。
- payload:
```json
{
  "character_id": "my_oc_test",
  "files": {
    "profile.yml": "REQ~most_called_name: 测试酱\nSIG~gender: 未知\nSIG~age: 未知\nSIG~description: 一个胆小但内心善良的原创角色。",
    "personality.yml": "REQ~core_traits:\n  - 胆小\n  - 善良\nSIG~fearful: 容易害怕，面对危险会选择逃避或躲藏。\nSIG~kind: 虽然胆小，但看到别人需要帮助时会鼓起勇气伸出援手。"
  },
  "display_name": "测试酱"
}
```
- 契约解析: ✅ 通过
- 警告: ['该动作缺少 sources；宁缺勿错，请勿编造依据']

### 步骤 ? · plan

- diff (审批预览):
```diff
+ === [新建] C:\Users\johnf\AppData\Local\Temp\live2be_e2e_mg7w8bid\config\characters\my_oc_test\profile.yml ===
+ REQ~most_called_name: 测试酱
+ SIG~gender: 未知
+ SIG~age: 未知
+ SIG~description: 一个胆小但内心善良的原创角色。
+ === [新建] C:\Users\johnf\AppData\Local\Temp\live2be_e2e_mg7w8bid\config\characters\my_oc_test\personality.yml ===
+ REQ~core_traits:
+   - 胆小
+   - 善良
+ SIG~fearful: 容易害怕，面对危险会选择逃避或躲藏。
+ SIG~kind: 虽然胆小，但看到别人需要帮助时会鼓起勇气伸出援手。
```

### 步骤 ? · decision

- 审批决策: **approved**
- 执行结果: ✅ 已创建角色 my_oc_test: profile.yml, personality.yml

### 步骤 2 · LLM 动作

- 动作: **done**  (审批: `never`)
- summary: 角色创建完成，等待你的下一步指示。
- 契约解析: ✅ 通过

**落盘结果** ✅: 角色已创建，profile.yml 内容：

```yaml
REQ~most_called_name: 测试酱
SIG~gender: 未知
SIG~age: 未知
SIG~description: 一个胆小但内心善良的原创角色。
```

## 任务 2：查询角色资料

**用户输入**: 帮我查一下《蔚蓝档案》里伊草遥香这个角色在萌娘百科上的资料。

### 步骤 0 · LLM 动作

- 动作: **fetch_url**  (审批: `never`)
- summary: 正在从萌娘百科获取《蔚蓝档案》角色伊草遥香的资料。
- payload:
```json
{
  "url": "https://zh.moegirl.org.cn/伊草遥香",
  "max_chars": 50000
}
```
- 契约解析: ✅ 通过

### 步骤 ? · fetch

- 抓取: `https://zh.moegirl.org.cn/伊草遥香` → 16633 字符, 已回灌给 LLM

### 步骤 1 · LLM 动作

- 动作: **done**  (审批: `never`)
- summary: 已获取伊草遥香资料，等待你的下一步指示。
- payload:
```json
{
  "message": "伊草遥香：格黑娜学园便利屋68成员，紫发紫瞳，15岁，身高157cm，生日5月13日，胆小自卑但忠诚于亚瑠，兴趣是种杂草。详细资料见萌娘百科。"
}
```
- 契约解析: ✅ 通过


## 结论（任务 1+2 汇总）

| 指标 | 任务 1（创建 OC） | 任务 2（查资料） |
|------|------------------|------------------|
| LLM 动作轮次 | 3（无效回灌 → create → done） | 2（fetch → done） |
| 契约解析失败 | 1（basis 类型错, 自动回灌修正后通过） | 0 |
| 写动作 | `create_character` → 审批批准 → 落盘 ✅ | — |
| 只读工具 | — | `fetch_url` 抓取 16633 字符回灌 ✅ |
| 执行层拦截 | 0 | 0 |

**关键验证点**
- ✅ **回灌修正**：任务 1 步骤 0，LLM 首次输出 `basis` 类型错 + profile 为空，契约层正确拒绝并回灌错误 → LLM 步骤 1 修正后通过
- ✅ **输入层裁剪**：`fetch_url`/`done` 的 schema 不含 sources/basis，LLM 从未为其输出多余依据字段
- ✅ **执行层**：create 真实落盘（profile + personality 写入）、fetch 真实抓取萌娘百科
- ✅ **跨轮记忆**：done 的 message 正确总结了抓取内容，证明 fetch 结果成功回灌给 LLM
- ⚠️ **已修复的真实 bug**：`client.chat(response_format="json_object")` 返回 dict（client 内置 JSON 清洗），而 agent 原用 `parse_action_text`（吃原始文本）导致 `AttributeError`——已改为直接 `registry.parse(response)`
- ⚠️ 报告小瑕疵：结论统计原只覆盖任务 2（任务 2 前重置了 trace），已手动修正

**观察**
- OC 场景验证通过：无 sources（宁缺勿错 warning 提示）、依据靠 basis，契约层不阻断
- LLM 对 `REQ~`/`SIG~` 前缀约定理解正确（自主生成了 `REQ~core_traits` 等自定义必填字段）
