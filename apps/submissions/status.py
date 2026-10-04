"""提交判题状态常量（唯一出处）。

``execution_status`` 在模型里是宽松的 ``CharField``，业务上只有下面几个取值。
集中定义可以避免各模块散落字符串字面量导致的拼写漂移。

- ``PENDING``：已落库、等待判题
- ``ACCEPTED`` / ``WRONG_ANSWER``：判题完成的确定性结果（可以缓存）
- ``ERROR``：判题服务故障、建表失败或队列不可用
- ``TIMEOUT``：仅旧版兼容接口可能返回，新链路统一按 ``ERROR`` 处理
"""

PENDING = 'PENDING'
ACCEPTED = 'ACCEPTED'
WRONG_ANSWER = 'WRONG_ANSWER'
ERROR = 'ERROR'
TIMEOUT = 'TIMEOUT'

#: 判题完成后可以安全缓存的状态；瞬时 ERROR / TIMEOUT 不缓存
CACHEABLE_STATUSES = (ACCEPTED, WRONG_ANSWER)

__all__ = [
    'PENDING',
    'ACCEPTED',
    'WRONG_ANSWER',
    'ERROR',
    'TIMEOUT',
    'CACHEABLE_STATUSES',
]
