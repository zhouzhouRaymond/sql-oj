"""容器池的轻量单元测试（不依赖 Docker）。

运行：``python judge_service/test_container_pool.py``
"""
import unittest
from unittest import mock

from container_pool import ContainerPool, PooledContainer


class FakeContainer:
    """模拟 docker SDK 的 Container（仅暴露端口映射相关接口）。"""

    def __init__(self, ports):
        self.name = "c"
        self.id = "0123456789abcdef"
        self.attrs = {"NetworkSettings": {"Ports": {"5432/tcp": ports}}}

    def reload(self):
        return None


class HostPortParsingTests(unittest.TestCase):
    def test_reads_host_port(self):
        self.assertEqual(
            ContainerPool._host_port(FakeContainer([{"HostPort": "32768"}])), 32768
        )

    def test_no_binding_returns_none(self):
        self.assertIsNone(ContainerPool._host_port(FakeContainer(None)))
        self.assertIsNone(ContainerPool._host_port(FakeContainer([])))

    def test_malformed_binding_returns_none(self):
        self.assertIsNone(ContainerPool._host_port(FakeContainer([{"HostPort": ""}])))


class ReuseTests(unittest.TestCase):
    def test_acquire_release_reuses_same_container(self):
        pool = ContainerPool(size=1, max_size=1)
        container = PooledContainer(name="c1", container_id="abc", host="h", port=1)
        created = []

        def fake_create():
            created.append(1)
            return container

        with mock.patch.object(pool, "_create", side_effect=fake_create), \
                mock.patch.object(pool, "_reset", return_value=None), \
                mock.patch.object(pool, "_destroy", return_value=None):
            first = pool.acquire()
            pool.release(first)
            second = pool.acquire()

        self.assertIs(first, second)
        self.assertEqual(len(created), 1)  # 复用而非新建
        self.assertEqual(pool.stats()["reused"], 1)

    def test_unhealthy_container_is_replaced(self):
        pool = ContainerPool(size=1, max_size=1)
        container = PooledContainer(name="c1", container_id="abc", host="h", port=1)
        destroyed = []
        with mock.patch.object(pool, "_destroy", side_effect=lambda name: destroyed.append(name)):
            pool.release(container, healthy=False)
        self.assertEqual(destroyed, ["c1"])
        self.assertEqual(pool.stats()["total"], 0)

    def test_disabled_pool_has_zero_size(self):
        pool = ContainerPool(size=0, max_size=0)
        pool.start()  # 不应启动任何容器/线程
        self.assertEqual(pool.stats()["total"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
