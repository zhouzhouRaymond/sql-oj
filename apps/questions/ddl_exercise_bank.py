"""DDL 练习题题库（schema 判题，Phase 1 能力范围内）。

每道题包含：

- ``reference_sql``：标准答案。导入时会把它（连同 ``setup_sql``）送到判题服务的
  ``/introspect``，自动生成 ``expected_schema``——所以教师的期望结构与判题
  引擎的规范化规则永远一致；
- ``probes``：行为探针，用来验证约束真的生效（唯一/非空/CHECK/外键）；
- ``setup_sql``：ALTER 类题目的前置表结构（学生只写 ALTER）。

``supported=False`` 的题目只作为"能力路线图"保留，导入时会跳过（当前所有题目
均已可自动判题）。

导入：``python manage.py seed_ddl_exercises --verify``
"""
from __future__ import annotations

from typing import Any, Dict, List

CATEGORIES = {
    'create-table': '创建表（列/类型/默认值/非空）',
    'keys': '主键与唯一键（含复合键）',
    'constraints': 'CHECK 约束',
    'relationships': '外键与表关系（1:1 / 1:N / M:N / 自引用）',
    'alter': 'ALTER TABLE 修改结构',
    'indexes': '索引',
}

DIFFICULTIES = ('easy', 'medium', 'hard')


def _probe(
    sql: str,
    expect: str = 'ok',
    error_code: str | None = None,
    description: str = '',
) -> Dict[str, Any]:
    """构造一条行为探针；多语句脚本用分号分隔（整体在一个 SAVEPOINT 内）。

    注意：探针之间互相隔离，但自增序列的推进不会随回滚撤销。因此探针里
    不要硬编码自增主键的值，需要用 id 时请用子查询（见自引用关系那题）。
    """
    probe: Dict[str, Any] = {'sql': sql, 'expect': expect, 'description': description}
    if error_code:
        probe['error_code'] = error_code
    return probe


DDL_EXERCISES: List[Dict[str, Any]] = [
    # ------------------------------------------------------------------ #
    # 创建表：列 / 类型 / 默认值 / 非空
    # ------------------------------------------------------------------ #
    {
        'slug': 'ct-users',
        'title': 'DDL 建表：用户表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 users 表：id 为自增整数主键；username 为长度 50 的非空字符串且唯一；'
            'created_at 为非空时间戳，默认当前时间。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE users ('
            'id SERIAL PRIMARY KEY, '
            'username VARCHAR(50) NOT NULL UNIQUE, '
            'created_at TIMESTAMP NOT NULL DEFAULT now());'
        ),
        'probes': [
            _probe("INSERT INTO users (username) VALUES ('alice')", description='插入合法用户'),
            _probe(
                "INSERT INTO users (username) VALUES ('bob');"
                "INSERT INTO users (username) VALUES ('bob')",
                expect='error', error_code='23505', description='用户名唯一',
            ),
            _probe(
                'INSERT INTO users (username) VALUES (NULL)',
                expect='error', error_code='23502', description='用户名非空',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-books',
        'title': 'DDL 建表：图书表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 books 表：id 自增主键；title 为长度 200 的非空字符串；'
            'price 为 NUMERIC(10,2)、非空、默认 0；published_year 为可空整数。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE books ('
            'id SERIAL PRIMARY KEY, '
            'title VARCHAR(200) NOT NULL, '
            'price NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'published_year INTEGER);'
        ),
        'probes': [
            _probe("INSERT INTO books (title) VALUES ('SQL 入门')", description='只填必填列也能插入'),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-students',
        'title': 'DDL 建表：学号主键的学生表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 students 表：stu_no 为长度 20 的字符串主键；name 为长度 50 的非空字符串；'
            'gender 为长度 1 的字符串（可空）；birth_date 为可空日期。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE students ('
            'stu_no VARCHAR(20) PRIMARY KEY, '
            'name VARCHAR(50) NOT NULL, '
            'gender CHAR(1), '
            'birth_date DATE);'
        ),
        'probes': [
            _probe(
                "INSERT INTO students (stu_no, name) VALUES ('S001', '张三')",
                description='插入合法学生',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-products',
        'title': 'DDL 建表：库存非负的商品表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 products 表：id 自增主键；name 为长度 100 的非空字符串；'
            'stock 为非空整数、默认 0，且不允许为负数。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE products ('
            'id SERIAL PRIMARY KEY, '
            'name VARCHAR(100) NOT NULL, '
            'stock INTEGER NOT NULL DEFAULT 0, '
            'CONSTRAINT stock_non_negative CHECK (stock >= 0));'
        ),
        'probes': [
            _probe(
                "INSERT INTO products (name, stock) VALUES ('铅笔', -1)",
                expect='error', error_code='23514', description='库存不能为负',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-employees',
        'title': 'DDL 建表：员工表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 employees 表：id 自增主键；name 为长度 50 的非空字符串；'
            'salary 为 NUMERIC(10,2)、非空、默认 0；email 为长度 100 的唯一字符串（可空）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE employees ('
            'id SERIAL PRIMARY KEY, '
            'name VARCHAR(50) NOT NULL, '
            'salary NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'email VARCHAR(100) UNIQUE);'
        ),
        'probes': [
            _probe(
                "INSERT INTO employees (name, email) VALUES ('a', 'a@x.com');"
                "INSERT INTO employees (name, email) VALUES ('b', 'a@x.com')",
                expect='error', error_code='23505', description='邮箱唯一',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-courses',
        'title': 'DDL 建表：学分范围受限的课程表',
        'category': 'create-table',
        'difficulty': 'medium',
        'description': (
            '创建 courses 表：code 为长度 6 的字符串主键；title 为长度 100 的非空字符串；'
            'credits 为 SMALLINT、非空、默认 3，且取值在 1 到 10 之间。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE courses ('
            'code CHAR(6) PRIMARY KEY, '
            'title VARCHAR(100) NOT NULL, '
            'credits SMALLINT NOT NULL DEFAULT 3, '
            'CONSTRAINT credits_range CHECK (credits BETWEEN 1 AND 10));'
        ),
        'probes': [
            _probe(
                "INSERT INTO courses (code, title, credits) VALUES ('C0001', '数据库', 0)",
                expect='error', error_code='23514', description='学分下限',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-movies',
        'title': 'DDL 建表：时长必须为正的电影表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 movies 表：id 自增主键；title 为长度 200 的非空字符串；'
            'duration_minutes 为非空整数且必须大于 0。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE movies ('
            'id SERIAL PRIMARY KEY, '
            'title VARCHAR(200) NOT NULL, '
            'duration_minutes INTEGER NOT NULL, '
            'CONSTRAINT duration_positive CHECK (duration_minutes > 0));'
        ),
        'probes': [
            _probe(
                "INSERT INTO movies (title, duration_minutes) VALUES ('x', 0)",
                expect='error', error_code='23514', description='时长必须为正',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'ct-sensor-logs',
        'title': 'DDL 建表：传感器读数表',
        'category': 'create-table',
        'difficulty': 'easy',
        'description': (
            '创建 sensor_logs 表：id 自增主键；sensor_id 为长度 30 的非空字符串；'
            'reading 为 NUMERIC(5,2) 且非空；recorded_at 为非空时间戳、默认当前时间。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE sensor_logs ('
            'id SERIAL PRIMARY KEY, '
            'sensor_id VARCHAR(30) NOT NULL, '
            'reading NUMERIC(5,2) NOT NULL, '
            'recorded_at TIMESTAMP NOT NULL DEFAULT now());'
        ),
        'probes': [
            _probe(
                "INSERT INTO sensor_logs (sensor_id, reading) VALUES ('S1', 12.5)",
                description='插入合法读数',
            ),
        ],
        'supported': True,
    },

    # ------------------------------------------------------------------ #
    # 主键与唯一键
    # ------------------------------------------------------------------ #
    {
        'slug': 'key-composite-pk',
        'title': 'DDL 键：复合主键选课表',
        'category': 'keys',
        'difficulty': 'medium',
        'description': (
            '创建 enrollments 表：student_id 与 course_id 为两个非空整数，'
            '共同组成复合主键；enrolled_at 为非空时间戳、默认当前时间。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE enrollments ('
            'student_id INTEGER NOT NULL, '
            'course_id INTEGER NOT NULL, '
            'enrolled_at TIMESTAMP NOT NULL DEFAULT now(), '
            'PRIMARY KEY (student_id, course_id));'
        ),
        'probes': [
            _probe(
                'INSERT INTO enrollments (student_id, course_id) VALUES (1, 1);'
                'INSERT INTO enrollments (student_id, course_id) VALUES (1, 1)',
                expect='error', error_code='23505', description='复合主键唯一',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'key-order-items',
        'title': 'DDL 键：订单行复合主键',
        'category': 'keys',
        'difficulty': 'medium',
        'description': (
            '创建 order_items 表：order_id 与 line_no 为非空整数并组成复合主键；'
            'quantity 为非空整数、默认 1，且必须大于 0。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE order_items ('
            'order_id INTEGER NOT NULL, '
            'line_no INTEGER NOT NULL, '
            'quantity INTEGER NOT NULL DEFAULT 1, '
            'PRIMARY KEY (order_id, line_no), '
            'CONSTRAINT quantity_positive CHECK (quantity > 0));'
        ),
        'probes': [
            _probe(
                'INSERT INTO order_items (order_id, line_no, quantity) VALUES (1, 1, 0)',
                expect='error', error_code='23514', description='数量必须大于 0',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'key-unique-named',
        'title': 'DDL 键：命名唯一约束',
        'category': 'keys',
        'difficulty': 'medium',
        'description': (
            '创建 accounts 表：id 自增主键；email 为长度 100 的非空字符串；'
            '为 email 添加名为 uq_accounts_email 的唯一约束。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE accounts ('
            'id SERIAL PRIMARY KEY, '
            'email VARCHAR(100) NOT NULL, '
            'CONSTRAINT uq_accounts_email UNIQUE (email));'
        ),
        'probes': [
            _probe(
                "INSERT INTO accounts (email) VALUES ('a@x.com');"
                "INSERT INTO accounts (email) VALUES ('a@x.com')",
                expect='error', error_code='23505', description='邮箱唯一',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'key-composite-unique',
        'title': 'DDL 键：座位组合唯一',
        'category': 'keys',
        'difficulty': 'medium',
        'description': (
            '创建 seats 表：id 自增主键；hall_id 与 seat_no 为非空整数；'
            '(hall_id, seat_no) 组合唯一。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE seats ('
            'id SERIAL PRIMARY KEY, '
            'hall_id INTEGER NOT NULL, '
            'seat_no INTEGER NOT NULL, '
            'UNIQUE (hall_id, seat_no));'
        ),
        'probes': [
            _probe(
                'INSERT INTO seats (hall_id, seat_no) VALUES (1, 10);'
                'INSERT INTO seats (hall_id, seat_no) VALUES (1, 10)',
                expect='error', error_code='23505', description='同一影厅座位号唯一',
            ),
            _probe(
                'INSERT INTO seats (hall_id, seat_no) VALUES (1, 11);'
                'INSERT INTO seats (hall_id, seat_no) VALUES (2, 11)',
                description='不同影厅可有相同座位号',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'key-isbn-unique',
        'title': 'DDL 键：ISBN 唯一',
        'category': 'keys',
        'difficulty': 'easy',
        'description': (
            '创建 book_editions 表：id 自增主键；isbn 为长度 13 的非空唯一字符串；'
            'title 为长度 200 的非空字符串。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE book_editions ('
            'id SERIAL PRIMARY KEY, '
            'isbn VARCHAR(13) NOT NULL UNIQUE, '
            'title VARCHAR(200) NOT NULL);'
        ),
        'probes': [
            _probe(
                "INSERT INTO book_editions (isbn, title) VALUES ('9780000000001', 'a');"
                "INSERT INTO book_editions (isbn, title) VALUES ('9780000000001', 'b')",
                expect='error', error_code='23505', description='ISBN 唯一',
            ),
            _probe(
                "INSERT INTO book_editions (isbn, title) VALUES (NULL, 'c')",
                expect='error', error_code='23502', description='ISBN 非空',
            ),
        ],
        'supported': True,
    },

    # ------------------------------------------------------------------ #
    # CHECK 约束
    # ------------------------------------------------------------------ #
    {
        'slug': 'chk-balance',
        'title': 'DDL 约束：账户余额非负',
        'category': 'constraints',
        'difficulty': 'easy',
        'description': (
            '创建 accounts_balance 表：id 自增主键；balance 为 NUMERIC(12,2)、'
            '非空、默认 0，且不允许为负数。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE accounts_balance ('
            'id SERIAL PRIMARY KEY, '
            'balance NUMERIC(12,2) NOT NULL DEFAULT 0, '
            'CONSTRAINT balance_non_negative CHECK (balance >= 0));'
        ),
        'probes': [
            _probe(
                'INSERT INTO accounts_balance (balance) VALUES (-0.01)',
                expect='error', error_code='23514', description='余额不能为负',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'chk-time-range',
        'title': 'DDL 约束：结束时间晚于开始时间',
        'category': 'constraints',
        'difficulty': 'medium',
        'description': (
            '创建 events 表：id 自增主键；start_at 与 end_at 为非空时间戳；'
            '要求 end_at 严格晚于 start_at。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE events ('
            'id SERIAL PRIMARY KEY, '
            'start_at TIMESTAMP NOT NULL, '
            'end_at TIMESTAMP NOT NULL, '
            'CONSTRAINT time_range CHECK (end_at > start_at));'
        ),
        'probes': [
            _probe(
                "INSERT INTO events (start_at, end_at) "
                "VALUES ('2026-01-01 10:00', '2026-01-01 09:00')",
                expect='error', error_code='23514', description='结束时间必须晚于开始时间',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'chk-rating',
        'title': 'DDL 约束：评分 1~5',
        'category': 'constraints',
        'difficulty': 'easy',
        'description': (
            '创建 ratings 表：id 自增主键；score 为非空整数，取值必须在 1 到 5 之间。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE ratings ('
            'id SERIAL PRIMARY KEY, '
            'score INTEGER NOT NULL, '
            'CONSTRAINT rating_range CHECK (score BETWEEN 1 AND 5));'
        ),
        'probes': [
            _probe('INSERT INTO ratings (score) VALUES (6)',
                   expect='error', error_code='23514', description='评分上限'),
            _probe('INSERT INTO ratings (score) VALUES (3)', description='合法评分'),
        ],
        'supported': True,
    },
    {
        'slug': 'chk-percent',
        'title': 'DDL 约束：折扣百分比 0~100',
        'category': 'constraints',
        'difficulty': 'medium',
        'description': (
            '创建 discounts 表：id 自增主键；percent 为 NUMERIC(5,2) 且非空；'
            '取值必须在 0 到 100 之间（含端点）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE discounts ('
            'id SERIAL PRIMARY KEY, '
            'percent NUMERIC(5,2) NOT NULL, '
            'CONSTRAINT percent_range CHECK (percent >= 0 AND percent <= 100));'
        ),
        'probes': [
            _probe('INSERT INTO discounts (percent) VALUES (101)',
                   expect='error', error_code='23514', description='折扣上限'),
        ],
        'supported': True,
    },

    # ------------------------------------------------------------------ #
    # 外键与表关系
    # ------------------------------------------------------------------ #
    {
        'slug': 'rel-set-null',
        'title': 'DDL 关系：班级与学生（SET NULL）',
        'category': 'relationships',
        'difficulty': 'medium',
        'description': (
            '创建 classes 表（id 自增主键，name 长度 50 非空）与 students 表'
            '（id 自增主键，name 长度 50 非空，class_id 可空整数外键指向 classes.id，'
            '删除班级时把学生班级置空）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE classes (id SERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL);'
            'CREATE TABLE students ('
            'id SERIAL PRIMARY KEY, '
            'name VARCHAR(50) NOT NULL, '
            'class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL);'
        ),
        'probes': [
            _probe(
                'INSERT INTO students (name, class_id) VALUES (\'s\', 999)',
                expect='error', error_code='23503', description='班级外键必须存在',
            ),
            _probe(
                "INSERT INTO classes (name) VALUES ('A');"
                'INSERT INTO students (name, class_id) VALUES (\'s\', 1);'
                'DELETE FROM classes WHERE id = 1',
                description='删除班级时外键置空',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'rel-cascade',
        'title': 'DDL 关系：作者与图书（CASCADE）',
        'category': 'relationships',
        'difficulty': 'medium',
        'description': (
            '创建 authors 表（id 自增主键，name 长度 50 非空）与 books 表'
            '（id 自增主键，title 长度 200 非空，author_id 非空整数外键指向 authors.id，'
            '删除作者时级联删除其图书）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE authors (id SERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL);'
            'CREATE TABLE books ('
            'id SERIAL PRIMARY KEY, '
            'title VARCHAR(200) NOT NULL, '
            'author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE);'
        ),
        'probes': [
            _probe('INSERT INTO books (title, author_id) VALUES (\'x\', 999)',
                   expect='error', error_code='23503', description='作者外键必须存在'),
            _probe(
                "INSERT INTO authors (name) VALUES ('a');"
                'INSERT INTO books (title, author_id) VALUES (\'b\', 1);'
                'DELETE FROM authors WHERE id = 1',
                description='删除作者时级联删除图书',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'rel-restrict',
        'title': 'DDL 关系：客户与订单（RESTRICT）',
        'category': 'relationships',
        'difficulty': 'hard',
        'description': (
            '创建 customers 表（id 自增主键，name 长度 50 非空）与 orders 表'
            '（id 自增主键，amount NUMERIC(10,2) 非空，customer_id 非空整数外键指向'
            'customers.id，存在订单时禁止删除客户）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE customers (id SERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL);'
            'CREATE TABLE orders ('
            'id SERIAL PRIMARY KEY, '
            'amount NUMERIC(10,2) NOT NULL, '
            'customer_id INTEGER NOT NULL '
            'REFERENCES customers(id) ON DELETE RESTRICT);'
        ),
        'probes': [
            _probe('INSERT INTO orders (amount, customer_id) VALUES (10, 999)',
                   expect='error', error_code='23503', description='客户外键必须存在'),
            _probe(
                "INSERT INTO customers (name) VALUES ('c');"
                'INSERT INTO orders (amount, customer_id) VALUES (10, 1);'
                'DELETE FROM customers WHERE id = 1',
                expect='error', error_code='23503', description='存在订单时禁止删除客户',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'rel-one-to-one',
        'title': 'DDL 关系：用户与档案（1:1）',
        'category': 'relationships',
        'difficulty': 'hard',
        'description': (
            '创建 users_1to1 表（id 自增主键，username 长度 50 非空唯一）与 profiles 表'
            '（id 自增主键，bio 可空文本，user_id 非空整数、唯一、外键指向 users_1to1.id，'
            '删除用户时级联删除档案）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE users_1to1 ('
            'id SERIAL PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE);'
            'CREATE TABLE profiles ('
            'id SERIAL PRIMARY KEY, '
            'bio TEXT, '
            'user_id INTEGER NOT NULL UNIQUE '
            'REFERENCES users_1to1(id) ON DELETE CASCADE);'
        ),
        'probes': [
            _probe(
                "INSERT INTO users_1to1 (username) VALUES ('u');"
                'INSERT INTO profiles (user_id) VALUES (1);'
                'INSERT INTO profiles (user_id) VALUES (1)',
                expect='error', error_code='23505', description='一个用户只能有一个档案',
            ),
            _probe('INSERT INTO profiles (user_id) VALUES (999)',
                   expect='error', error_code='23503', description='档案必须属于已存在用户'),
        ],
        'supported': True,
    },
    {
        'slug': 'rel-many-to-many',
        'title': 'DDL 关系：学生选课（M:N 连接表）',
        'category': 'relationships',
        'difficulty': 'hard',
        'description': (
            '创建 students_mn（id 自增主键，name 长度 50 非空）、courses_mn（id 自增主键，'
            'title 长度 100 非空）与连接表 enrollments_mn（student_id、course_id 为非空整数，'
            '组成复合主键，两者分别外键指向对应表并级联删除）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE students_mn (id SERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL);'
            'CREATE TABLE courses_mn (id SERIAL PRIMARY KEY, title VARCHAR(100) NOT NULL);'
            'CREATE TABLE enrollments_mn ('
            'student_id INTEGER NOT NULL REFERENCES students_mn(id) ON DELETE CASCADE, '
            'course_id INTEGER NOT NULL REFERENCES courses_mn(id) ON DELETE CASCADE, '
            'PRIMARY KEY (student_id, course_id));'
        ),
        'probes': [
            _probe('INSERT INTO enrollments_mn (student_id, course_id) VALUES (1, 1)',
                   expect='error', error_code='23503', description='选课记录必须引用已存在的学生'),
            _probe(
                'INSERT INTO students_mn (name) VALUES (\'s\');'
                'INSERT INTO courses_mn (title) VALUES (\'c\');'
                'INSERT INTO enrollments_mn (student_id, course_id) VALUES (1, 1);'
                'DELETE FROM students_mn WHERE id = 1',
                description='删除学生级联删除选课记录',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'rel-self-reference',
        'title': 'DDL 关系：员工上下级（自引用）',
        'category': 'relationships',
        'difficulty': 'hard',
        'description': (
            '创建 employees_self 表：id 自增主键；name 长度 50 非空；manager_id 为可空整数，'
            '外键指向本表 id（删除上级时把下级的 manager_id 置空）。'
        ),
        'setup_sql': '',
        'reference_sql': (
            'CREATE TABLE employees_self ('
            'id SERIAL PRIMARY KEY, '
            'name VARCHAR(50) NOT NULL, '
            'manager_id INTEGER REFERENCES employees_self(id) ON DELETE SET NULL);'
        ),
        'probes': [
            _probe('INSERT INTO employees_self (name, manager_id) VALUES (\'a\', 999)',
                   expect='error', error_code='23503', description='上级必须已存在'),
            _probe(
                "INSERT INTO employees_self (name) VALUES ('boss');"
                "INSERT INTO employees_self (name, manager_id) "
                "VALUES ('worker', (SELECT id FROM employees_self WHERE name = 'boss'));"
                "DELETE FROM employees_self WHERE name = 'boss'",
                description='删除上级时下级保留',
            ),
        ],
        'supported': True,
    },

    # ------------------------------------------------------------------ #
    # ALTER TABLE
    # ------------------------------------------------------------------ #
    {
        'slug': 'alter-add-column',
        'title': 'DDL ALTER：为商品补一列描述',
        'category': 'alter',
        'difficulty': 'easy',
        'description': (
            '已有 products_alter 表（id 自增主键，name 长度 100 非空）。'
            '为它增加一个可空文本列 description。'
        ),
        'setup_sql': (
            'CREATE TABLE products_alter (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL);'
        ),
        'reference_sql': 'ALTER TABLE products_alter ADD COLUMN description TEXT;',
        'probes': [
            _probe("INSERT INTO products_alter (name, description) VALUES ('a', 'd')",
                   description='新列可写入'),
        ],
        'supported': True,
    },
    {
        'slug': 'alter-set-not-null',
        'title': 'DDL ALTER：邮箱改为非空',
        'category': 'alter',
        'difficulty': 'medium',
        'description': (
            '已有 customers_alter 表（id 自增主键，email 长度 100 的可空字符串）。'
            '把 email 修改为非空。'
        ),
        'setup_sql': (
            'CREATE TABLE customers_alter (id SERIAL PRIMARY KEY, email VARCHAR(100));'
        ),
        'reference_sql': 'ALTER TABLE customers_alter ALTER COLUMN email SET NOT NULL;',
        'probes': [
            _probe('INSERT INTO customers_alter (email) VALUES (NULL)',
                   expect='error', error_code='23502', description='邮箱非空'),
        ],
        'supported': True,
    },
    {
        'slug': 'alter-add-unique',
        'title': 'DDL ALTER：给会员邮箱加唯一约束',
        'category': 'alter',
        'difficulty': 'medium',
        'description': (
            '已有 members 表（id 自增主键，email 长度 100 的非空字符串）。'
            '为 email 添加唯一约束（约束名 uq_members_email）。'
        ),
        'setup_sql': (
            'CREATE TABLE members (id SERIAL PRIMARY KEY, email VARCHAR(100) NOT NULL);'
        ),
        'reference_sql': (
            'ALTER TABLE members ADD CONSTRAINT uq_members_email UNIQUE (email);'
        ),
        'probes': [
            _probe(
                "INSERT INTO members (email) VALUES ('a@x.com');"
                "INSERT INTO members (email) VALUES ('a@x.com')",
                expect='error', error_code='23505', description='邮箱唯一',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'alter-add-check',
        'title': 'DDL ALTER：给价格加非负检查',
        'category': 'alter',
        'difficulty': 'medium',
        'description': (
            '已有 items 表（id 自增主键，price 为 NUMERIC(10,2) 非空）。'
            '添加 CHECK 约束 price_non_negative，要求 price 不小于 0。'
        ),
        'setup_sql': (
            'CREATE TABLE items (id SERIAL PRIMARY KEY, price NUMERIC(10,2) NOT NULL);'
        ),
        'reference_sql': (
            'ALTER TABLE items ADD CONSTRAINT price_non_negative CHECK (price >= 0);'
        ),
        'probes': [
            _probe('INSERT INTO items (price) VALUES (-1)',
                   expect='error', error_code='23514', description='价格不能为负'),
        ],
        'supported': True,
    },
    {
        'slug': 'alter-add-foreign-key',
        'title': 'DDL ALTER：为订单补外键',
        'category': 'alter',
        'difficulty': 'hard',
        'description': (
            '已有 customers_alter2（id 自增主键）与 orders_alter（id 自增主键，'
            'customer_id 可空整数）。为 orders_alter.customer_id 添加外键，'
            '指向 customers_alter2.id，删除客户时级联删除订单（约束名 fk_orders_customer）。'
        ),
        'setup_sql': (
            'CREATE TABLE customers_alter2 (id SERIAL PRIMARY KEY);'
            'CREATE TABLE orders_alter (id SERIAL PRIMARY KEY, customer_id INTEGER);'
        ),
        'reference_sql': (
            'ALTER TABLE orders_alter ADD CONSTRAINT fk_orders_customer '
            'FOREIGN KEY (customer_id) REFERENCES customers_alter2(id) ON DELETE CASCADE;'
        ),
        'probes': [
            _probe('INSERT INTO orders_alter (customer_id) VALUES (999)',
                   expect='error', error_code='23503', description='客户外键必须存在'),
            _probe(
                'INSERT INTO customers_alter2 DEFAULT VALUES;'
                'INSERT INTO orders_alter (customer_id) VALUES (1);'
                'DELETE FROM customers_alter2 WHERE id = 1',
                description='删除客户级联删除订单',
            ),
        ],
        'supported': True,
    },

    # ------------------------------------------------------------------ #
    # 索引
    # ------------------------------------------------------------------ #
    {
        'slug': 'idx-unique-single',
        'title': 'DDL 索引：唯一索引保证邮箱不重复',
        'category': 'indexes',
        'difficulty': 'medium',
        'description': (
            '已有 users_idx 表（id 自增主键，email 长度 100 非空）。'
            '创建唯一索引 uq_users_idx_email，保证 email 不重复。'
        ),
        'setup_sql': (
            'CREATE TABLE users_idx (id SERIAL PRIMARY KEY, email VARCHAR(100) NOT NULL);'
        ),
        'reference_sql': (
            'CREATE UNIQUE INDEX uq_users_idx_email ON users_idx (email);'
        ),
        'probes': [
            _probe(
                "INSERT INTO users_idx (email) VALUES ('a@x.com');"
                "INSERT INTO users_idx (email) VALUES ('a@x.com')",
                expect='error', error_code='23505', description='唯一索引拒绝重复邮箱',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'idx-unique-composite',
        'title': 'DDL 索引：租户内编码唯一（复合唯一索引）',
        'category': 'indexes',
        'difficulty': 'hard',
        'description': (
            '已有 tenants 表（id 自增主键，tenant_id 与 code 均为非空整数/字符串）。'
            '创建唯一索引，使同一 tenant_id 下 code 不重复，不同租户可以有相同 code。'
        ),
        'setup_sql': (
            'CREATE TABLE tenants ('
            'id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, code VARCHAR(20) NOT NULL);'
        ),
        'reference_sql': (
            'CREATE UNIQUE INDEX uq_tenants_code ON tenants (tenant_id, code);'
        ),
        'probes': [
            _probe(
                "INSERT INTO tenants (tenant_id, code) VALUES (1, 'A');"
                "INSERT INTO tenants (tenant_id, code) VALUES (1, 'A')",
                expect='error', error_code='23505', description='同租户编码唯一',
            ),
            _probe(
                "INSERT INTO tenants (tenant_id, code) VALUES (1, 'A');"
                "INSERT INTO tenants (tenant_id, code) VALUES (2, 'A')",
                description='不同租户可用相同编码',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'idx-unique-partial',
        'title': 'DDL 索引：仅对生效记录做唯一（部分唯一索引）',
        'category': 'indexes',
        'difficulty': 'hard',
        'description': (
            '已有 inbox 表（id 自增主键，email 长度 100 非空，active 布尔非空默认真）。'
            '创建部分唯一索引，只要求 active 为真的记录里 email 不重复；'
            '已失效（active=false）的历史记录可以重复。'
        ),
        'setup_sql': (
            'CREATE TABLE inbox ('
            'id SERIAL PRIMARY KEY, '
            'email VARCHAR(100) NOT NULL, '
            'active BOOLEAN NOT NULL DEFAULT TRUE);'
        ),
        'reference_sql': (
            'CREATE UNIQUE INDEX uq_inbox_active_email ON inbox (email) WHERE active;'
        ),
        'probes': [
            _probe(
                "INSERT INTO inbox (email, active) VALUES ('a@x.com', TRUE);"
                "INSERT INTO inbox (email, active) VALUES ('a@x.com', TRUE)",
                expect='error', error_code='23505', description='生效记录邮箱唯一',
            ),
            _probe(
                "INSERT INTO inbox (email, active) VALUES ('b@x.com', TRUE);"
                "INSERT INTO inbox (email, active) VALUES ('b@x.com', FALSE)",
                description='失效记录可重复',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'idx-nonunique-created-at',
        'title': 'DDL 索引：为时间列建普通索引',
        'category': 'indexes',
        'difficulty': 'medium',
        'description': (
            '已有 logs 表（id 自增主键，created_at 非空时间戳）。'
            '为 created_at 创建普通索引 idx_logs_created_at。'
        ),
        'setup_sql': (
            'CREATE TABLE logs (id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL);'
        ),
        'reference_sql': 'CREATE INDEX idx_logs_created_at ON logs (created_at);',
        'probes': [],
        'supported': True,  # 由索引结构 diff 判题（列/方法/唯一性/条件）
    },
    {
        'slug': 'idx-expression-lower-email',
        'title': 'DDL 索引：邮箱大小写不敏感唯一（表达式索引）',
        'category': 'indexes',
        'difficulty': 'hard',
        'description': (
            '已有 users_expr 表（id 自增主键，email 长度 100 非空）。'
            '创建唯一索引，使邮箱在忽略大小写后仍然唯一'
            '（即 lower(email) 不能重复）。'
        ),
        'setup_sql': (
            'CREATE TABLE users_expr (id SERIAL PRIMARY KEY, email VARCHAR(100) NOT NULL);'
        ),
        'reference_sql': (
            'CREATE UNIQUE INDEX uq_users_expr_lower ON users_expr (lower(email));'
        ),
        'probes': [
            _probe(
                "INSERT INTO users_expr (email) VALUES ('a@x.com');"
                "INSERT INTO users_expr (email) VALUES ('A@x.com')",
                expect='error', error_code='23505',
                description='忽略大小写后邮箱唯一',
            ),
        ],
        'supported': True,
    },
    {
        'slug': 'idx-desc-nulls',
        'title': 'DDL 索引：按时间倒序（DESC NULLS LAST）',
        'category': 'indexes',
        'difficulty': 'hard',
        'description': (
            '已有 events_idx 表（id 自增主键，created_at 非空时间戳）。'
            '为 created_at 创建索引，按时间倒序、NULL 排在最后'
            '（索引名 idx_events_created_desc）。'
        ),
        'setup_sql': (
            'CREATE TABLE events_idx (id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL);'
        ),
        'reference_sql': (
            'CREATE INDEX idx_events_created_desc ON events_idx (created_at DESC NULLS LAST);'
        ),
        'probes': [],
        'supported': True,  # 由索引结构 diff 比对排序与 NULLS 位置
    },
]


def supported_exercises() -> List[Dict[str, Any]]:
    """返回当前判题能力可用的题目。"""
    return [item for item in DDL_EXERCISES if item.get('supported', True)]


def validate_bank() -> List[str]:
    """校验题库结构，返回问题列表（空列表表示通过）。"""
    problems: List[str] = []
    seen_slugs: set[str] = set()
    for index, item in enumerate(DDL_EXERCISES):
        label = item.get('slug') or f'#{index}'
        slug = item.get('slug')
        if not slug:
            problems.append(f'{label}: 缺少 slug')
        elif slug in seen_slugs:
            problems.append(f'{label}: slug 重复')
        seen_slugs.add(slug)
        for field in ('title', 'description', 'reference_sql'):
            if not str(item.get(field) or '').strip():
                problems.append(f'{label}: 缺少 {field}')
        if item.get('category') not in CATEGORIES:
            problems.append(f'{label}: 未知分类 {item.get("category")!r}')
        if item.get('difficulty') not in DIFFICULTIES:
            problems.append(f'{label}: 未知难度 {item.get("difficulty")!r}')
        for probe_index, probe in enumerate(item.get('probes') or []):
            probe_label = f'{label}.probes[{probe_index}]'
            if not str(probe.get('sql') or '').strip():
                problems.append(f'{probe_label}: 缺少 sql')
            if probe.get('expect') not in ('ok', 'error'):
                problems.append(f'{probe_label}: expect 必须是 ok/error')
            if probe.get('expect') == 'error' and 'error_code' in probe:
                if not str(probe['error_code']).isdigit():
                    problems.append(f'{probe_label}: error_code 必须是 SQLSTATE 数字')
    return problems
