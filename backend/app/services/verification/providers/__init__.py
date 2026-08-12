"""
核验 Provider 实现子包。

每个模块对应一种渠道 / 厂商的具体实现：

- ``id_format``：A，国标 18 位身份证格式与校验位（本地可完整执行）；
- ``id_two_factor``：B，二要素核验（默认 stub，未接入真实厂商）；
- ``id_real_person``：C，实人核验（默认 stub，未接入真实厂商）；
- ``sms_debug`` / ``sms_aliyun`` / ``sms_tencent``：短信发送三种实现；
- ``email_debug`` / ``email_resend`` / ``email_aliyun``：邮件发送三种实现。

路由/编排逻辑在上层 ``app.services.verification`` 包，本子包只负责单一 Provider 的实现细节。
"""

from __future__ import annotations
