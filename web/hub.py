"""web/hub.py — 线程安全事件缓冲 + channel 隔离。

worker 线程（AgentRunner）publish → asyncio 侧 SSE 生成器 snapshot(cursor) 轮询。
没有订阅/退订对象——每连接只持有一个本地游标, 断开即生成器结束,
无全局残留可泄漏（Cursor 模式自带生命周期管理）。

channel: IDE 用 "ide"; 未来角色扮演服务用别的 channel, 互不串流。
"""
from __future__ import annotations

import threading


class EventHub:
    """共享事件缓冲。发布线程安全; 消费端按游标增量拉取。"""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def publish(self, evt: dict) -> None:
        """发布一条事件（任意线程）。evt 为 AgentEvent.to_dict() 结构。"""
        with self._lock:
            self._events.append(evt)

    def snapshot(self, cursor: int) -> tuple[list[dict], int]:
        """返回 (cursor 之后的新事件, 最新游标)。SSE 轮询调用。"""
        with self._lock:
            return list(self._events[cursor:]), len(self._events)

    @property
    def cursor(self) -> int:
        with self._lock:
            return len(self._events)


class Hubs:
    """channel → EventHub 的惰性注册表。不同服务互不串流。"""

    def __init__(self) -> None:
        self._hubs: dict[str, EventHub] = {}
        self._lock = threading.Lock()

    def get(self, channel: str) -> EventHub:
        with self._lock:
            hub = self._hubs.get(channel)
            if hub is None:
                hub = self._hubs[channel] = EventHub()
            return hub


#: 全局单例（进程内唯一; IDE GUI 单 agent）
HUBS = Hubs()
