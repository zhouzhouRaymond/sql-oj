"""
导入上机课 11 道题目到数据库（PostgreSQL 适配版，含全面测试用例）
用法: python manage.py import_exercises [--teacher-id=1]
"""
from django.core.management.base import BaseCommand
from apps.questions.models import Question, Answer, TestCase
from apps.users.models import User

QUESTIONS = [
    # ========== 第 1 题：员工晋升 ==========
    {
        "title": "员工晋升",
        "description": (
            "## 员工晋升\n\n"
            "表 `Employees`：\n"
            "| Column Name | Type |\n"
            "|---|---|\n"
            "| employee_id | int (PK) |\n"
            "| name | varchar |\n"
            "| role | varchar ('Manager' / 'Staff') |\n\n"
            "表 `Incomes`：\n"
            "| Column Name | Type |\n"
            "|---|---|\n"
            "| id | int (PK) |\n"
            "| employee_id | int (FK) |\n"
            "| income_date | date |\n"
            "| income_type | varchar ('Salary' / 'Bonus' / 'Fine') |\n"
            "| amount | int (always positive) |\n\n"
            "公司计划从普通员工中提拔新的经理。\n\n"
            "规则：\n"
            "- 仅统计 2023-01-01 至 2023-06-30 期间的收入记录\n"
            "- 仅考虑 role = 'Staff' 的员工\n"
            "- 净收入 = Salary + Bonus - Fine\n\n"
            "请找出该时间范围内**净收入最高**的普通员工。"
            "若有多人并列最高，需全部返回。\n\n"
            "返回列：employee_id, name, net_income"
        ),
        "difficulty": "medium",
        "sample_input": "无",
        "sample_output": "2 | Bob | 6000",
        "create_table_sql": (
            "CREATE TABLE Employees (\n"
            "    employee_id INT PRIMARY KEY,\n"
            "    name VARCHAR(255),\n"
            "    role VARCHAR(50)\n"
            ");\n"
            "CREATE TABLE Incomes (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    employee_id INT,\n"
            "    income_date DATE,\n"
            "    income_type VARCHAR(50) CHECK (income_type IN ('Salary', 'Bonus', 'Fine')),\n"
            "    amount INT\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "WITH StaffIncome AS (\n"
                "    SELECT\n"
                "        e.employee_id,\n"
                "        e.name,\n"
                "        SUM(\n"
                "            CASE\n"
                "                WHEN i.income_type IN ('Salary', 'Bonus') THEN i.amount\n"
                "                WHEN i.income_type = 'Fine' THEN -i.amount\n"
                "                ELSE 0\n"
                "            END\n"
                "        ) AS net_income\n"
                "    FROM Employees e\n"
                "    JOIN Incomes i ON e.employee_id = i.employee_id\n"
                "    WHERE e.role = 'Staff'\n"
                "      AND i.income_date BETWEEN '2023-01-01' AND '2023-06-30'\n"
                "    GROUP BY e.employee_id, e.name\n"
                ")\n"
                "SELECT employee_id, name, net_income\n"
                "FROM StaffIncome\n"
                "WHERE net_income = (SELECT MAX(net_income) FROM StaffIncome);"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Employees (employee_id, name, role) VALUES (1, 'Alice', 'Staff'), (2, 'Bob', 'Staff'), (3, 'Charlie', 'Manager');"
                    "INSERT INTO Incomes (employee_id, income_date, income_type, amount) VALUES "
                    "(1, '2023-02-01', 'Salary', 5000), (1, '2023-03-01', 'Bonus', 500), (1, '2023-04-01', 'Fine', 500), "
                    "(2, '2023-02-01', 'Salary', 6000), (2, '2023-05-01', 'Bonus', 1000), (2, '2023-05-15', 'Fine', 1000), "
                    "(3, '2023-03-01', 'Salary', 10000);"
                ),
                "expected_output": "employee_id|name|net_income\n2|Bob|6000"
            }
        ],
    },
    # ========== 第 2 题：计算模型 AUC ==========
    {
        "title": "计算模型 AUC",
        "description": (
            "## 计算模型 AUC\n\n"
            "表 `predictions`：\n"
            "| Column Name | Type |\n"
            "|---|---|\n"
            "| id | int (PK) |\n"
            "| user_id | int |\n"
            "| item_id | int |\n"
            "| label | tinyint (1=正样本, 0=负样本) |\n"
            "| score | decimal(10,4) (越大越可能为正) |\n\n"
            "请计算该模型的 AUC。\n\n"
            "AUC 定义：随机取一个正样本和一个负样本——\n"
            "- 正样本 score > 负样本 score → 记 1 分\n"
            "- 相等 → 记 0.5 分\n"
            "- 小于 → 记 0 分\n"
            "AUC = 总得分 / (正负样本对数量)，结果保留 4 位小数。\n\n"
            "返回：auc"
        ),
        "difficulty": "easy",
        "sample_input": "无",
        "sample_output": "0.7500",
        "create_table_sql": (
            "CREATE TABLE predictions (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    user_id INT NOT NULL,\n"
            "    item_id INT NOT NULL,\n"
            "    label SMALLINT NOT NULL CHECK (label IN (0,1)),\n"
            "    score DECIMAL(10,4) NOT NULL\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "SELECT\n"
                "    ROUND(\n"
                "        SUM(\n"
                "            CASE\n"
                "                WHEN p.score > n.score THEN 1\n"
                "                WHEN p.score = n.score THEN 0.5\n"
                "                ELSE 0\n"
                "            END\n"
                "        ) / COUNT(*),\n"
                "        4\n"
                "    ) AS auc\n"
                "FROM predictions p\n"
                "JOIN predictions n\n"
                "  ON p.label = 1 AND n.label = 0;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO predictions (user_id, item_id, label, score) VALUES "
                    "(1, 1, 1, 0.9), (1, 2, 0, 0.5), (2, 1, 1, 0.8), (2, 3, 0, 0.85);"
                ),
                "expected_output": "auc\n0.7500"
            }
        ],
    },
    # ========== 第 3 题：观看天数统计 ==========
    {
        "title": "观看天数统计",
        "description": (
            "## 观看天数统计\n\n"
            "表 `mid_third_tag_vv_vt_daily`：\n"
            "| Column Name | Type |\n"
            "|---|---|\n"
            "| mid | bigint |\n"
            "| third_tag | varchar |\n"
            "| log_date | date |\n\n"
            "统计每个用户 (mid) 对每个 third_tag 在最近 14 天内的观看天数。\n"
            "- 统计范围：2023-07-01 <= log_date < 2023-07-15\n"
            "- 同一天多次观看只算 1 天\n"
            "- 表可能含重复行\n\n"
            "返回：user_id, third_tag, watch_days\n"
            "排序：user_id ASC, third_tag ASC"
        ),
        "difficulty": "easy",
        "sample_input": "无",
        "sample_output": "1001 | news | 1\n1001 | sports | 2\n1002 | sports | 1",
        "create_table_sql": (
            "CREATE TABLE mid_third_tag_vv_vt_daily (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    mid BIGINT NOT NULL,\n"
            "    third_tag VARCHAR(100) NOT NULL,\n"
            "    log_date DATE NOT NULL\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "SELECT\n"
                "    mid AS user_id,\n"
                "    third_tag,\n"
                "    COUNT(DISTINCT log_date) AS watch_days\n"
                "FROM mid_third_tag_vv_vt_daily\n"
                "WHERE log_date >= '2023-07-01'\n"
                "  AND log_date < '2023-07-15'\n"
                "GROUP BY mid, third_tag\n"
                "ORDER BY user_id, third_tag;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO mid_third_tag_vv_vt_daily (mid, third_tag, log_date) VALUES "
                    "(1001, 'sports', '2023-07-01'), (1001, 'sports', '2023-07-01'), "  # 故意加入重复行
                    "(1001, 'sports', '2023-07-02'), "
                    "(1001, 'news', '2023-07-02'), (1002, 'sports', '2023-07-01');"
                ),
                "expected_output": "user_id|third_tag|watch_days\n1001|news|1\n1001|sports|2\n1002|sports|1"
            }
        ],
    },
    # ========== 第 4 题：模型打分分布对比 ==========
    {
        "title": "模型打分分布对比",
        "description": (
            "## 模型打分分布对比\n\n"
            "表 `model_scores`：\n"
            "| Column Name | Type |\n"
            "|---|---|\n"
            "| user_id | bigint |\n"
            "| av_id | bigint |\n"
            "| model_group | varchar ('base' / 'exp') |\n"
            "| score | decimal |\n"
            "| active_level | int (1~10) |\n\n"
            "在不同 active_group × model_group 下，分别统计：\n"
            "- 基础指标：cnt, avg_score, std_score\n"
            "- 分位数：p10_score, p50_score, p90_score, p99_score\n\n"
            "活跃度分层：low(1~3), mid(4~7), high(8~10)\n"
            "仅保留 score ∈ [0, 1]\n"
            "浮点数保留 6 位小数\n\n"
            "排序：active_group ASC, model_group ASC"
        ),
        "difficulty": "hard",
        "sample_input": "无",
        "sample_output": "low | base | 2 | 0.650000 | 0.212132 | ...",
        "create_table_sql": (
            "CREATE TABLE model_scores (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    user_id BIGINT NOT NULL,\n"
            "    av_id BIGINT NOT NULL,\n"
            "    model_group VARCHAR(20) NOT NULL CHECK (model_group IN ('base', 'exp')),\n"
            "    score DECIMAL(10,6) NOT NULL,\n"
            "    active_level INT NOT NULL CHECK (active_level BETWEEN 1 AND 10)\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "WITH base AS (\n"
                "    SELECT\n"
                "        user_id, av_id, model_group, score,\n"
                "        CASE\n"
                "            WHEN active_level BETWEEN 1 AND 3 THEN 'low'\n"
                "            WHEN active_level BETWEEN 4 AND 7 THEN 'mid'\n"
                "            ELSE 'high'\n"
                "        END AS active_group\n"
                "    FROM model_scores\n"
                "    WHERE score BETWEEN 0 AND 1\n"
                "),\n"
                "ranked AS (\n"
                "    SELECT\n"
                "        active_group, model_group, score,\n"
                "        ROW_NUMBER() OVER (PARTITION BY active_group, model_group ORDER BY score) AS rn,\n"
                "        COUNT(*) OVER (PARTITION BY active_group, model_group) AS cnt_all\n"
                "    FROM base\n"
                "),\n"
                "agg AS (\n"
                "    SELECT\n"
                "        active_group, model_group,\n"
                "        COUNT(*) AS cnt,\n"
                "        AVG(score) AS avg_score,\n"
                "        STDDEV_SAMP(score) AS std_score\n"
                "    FROM base\n"
                "    GROUP BY active_group, model_group\n"
                "),\n"
                "quantiles AS (\n"
                "    SELECT\n"
                "        active_group, model_group,\n"
                "        MAX(CASE WHEN rn = CEIL(cnt_all * 0.10) THEN score END) AS p10_score,\n"
                "        MAX(CASE WHEN rn = CEIL(cnt_all * 0.50) THEN score END) AS p50_score,\n"
                "        MAX(CASE WHEN rn = CEIL(cnt_all * 0.90) THEN score END) AS p90_score,\n"
                "        MAX(CASE WHEN rn = CEIL(cnt_all * 0.99) THEN score END) AS p99_score\n"
                "    FROM ranked\n"
                "    GROUP BY active_group, model_group\n"
                ")\n"
                "SELECT\n"
                "    a.active_group, a.model_group, a.cnt,\n"
                "    ROUND(a.avg_score, 6) AS avg_score,\n"
                "    ROUND(a.std_score, 6) AS std_score,\n"
                "    ROUND(q.p10_score, 6) AS p10_score,\n"
                "    ROUND(q.p50_score, 6) AS p50_score,\n"
                "    ROUND(q.p90_score, 6) AS p90_score,\n"
                "    ROUND(q.p99_score, 6) AS p99_score\n"
                "FROM agg a\n"
                "JOIN quantiles q\n"
                "  ON a.active_group = q.active_group AND a.model_group = q.model_group\n"
                "ORDER BY a.active_group ASC, a.model_group ASC;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO model_scores (user_id, av_id, model_group, score, active_level) VALUES "
                    "(1, 1, 'base', 0.5, 2), (1, 2, 'base', 0.8, 2), (2, 1, 'exp', 0.6, 5);"
                ),
                "expected_output": (
                    "active_group|model_group|cnt|avg_score|std_score|p10_score|p50_score|p90_score|p99_score\n"
                    "low|base|2|0.650000|0.212132|0.500000|0.500000|0.800000|0.800000\n"   # 修正 p50 为 0.5
                    "mid|exp|1|0.600000||0.600000|0.600000|0.600000|0.600000"
                )
            }
        ],
    },
    # ========== 第 5 题：连续签到用户统计 ==========
    {
        "title": "连续签到用户统计",
        "description": (
            "## 连续签到用户统计\n\n"
            "表 `Users`：user_id (PK), user_name\n"
            "表 `Checkins`：user_id, checkin_date (PK: user_id + date)\n\n"
            "统计时间范围：2025-04-01 ~ 2025-04-07\n\n"
            "找出在这一周内**至少连续签到 3 天**的用户。\n"
            "- 同一用户同一天最多签到一次\n"
            "- 超出范围的记录不参与判断\n\n"
            "返回：user_id, user_name\n"
            "排序：user_id ASC"
        ),
        "difficulty": "medium",
        "sample_input": "无",
        "sample_output": "1 | Alice",
        "create_table_sql": (
            "CREATE TABLE Users (\n"
            "    user_id INT PRIMARY KEY,\n"
            "    user_name VARCHAR(50) NOT NULL\n"
            ");\n"
            "CREATE TABLE Checkins (\n"
            "    user_id INT NOT NULL,\n"
            "    checkin_date DATE NOT NULL,\n"
            "    PRIMARY KEY (user_id, checkin_date)\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "WITH cte AS (\n"
                "    SELECT\n"
                "        user_id, checkin_date,\n"
                "        checkin_date - INTERVAL '1 day' * ROW_NUMBER() OVER (\n"
                "            PARTITION BY user_id ORDER BY checkin_date\n"
                "        ) AS grp\n"
                "    FROM Checkins\n"
                "    WHERE checkin_date BETWEEN '2025-04-01' AND '2025-04-07'\n"
                "),\n"
                "seq AS (\n"
                "    SELECT user_id, grp, COUNT(*) AS consecutive_days\n"
                "    FROM cte\n"
                "    GROUP BY user_id, grp\n"
                "    HAVING COUNT(*) >= 3\n"
                ")\n"
                "SELECT u.user_id, u.user_name\n"
                "FROM seq s\n"
                "JOIN Users u ON s.user_id = u.user_id\n"
                "ORDER BY u.user_id;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Users (user_id, user_name) VALUES (1, 'Alice'), (2, 'Bob');"
                    "INSERT INTO Checkins (user_id, checkin_date) VALUES "
                    "(1, '2025-04-01'), (1, '2025-04-02'), (1, '2025-04-03'), "   # Alice 连续3天
                    "(2, '2025-04-01'), (2, '2025-04-03'), (2, '2025-04-05');"    # Bob 不连续但够3天
                ),
                "expected_output": "user_id|user_name\n1|Alice"
            }
        ],
    },
    # ========== 第 6 题：部门内第二高薪员工 ==========
    {
        "title": "部门内第二高薪员工",
        "description": (
            "## 部门内第二高薪员工\n\n"
            "表 `Departments`：department_id (PK), department_name\n"
            "表 `Employees`：employee_id (PK), employee_name, department_id (FK), salary\n\n"
            "找出每个部门中薪资排名第 2 的员工。\n"
            "- 按薪资从高到低排序\n"
            "- 使用不同薪资值的排名（DENSE_RANK）\n"
            "- 同一薪资并列则全部返回\n"
            "- 若部门不存在第 2 高薪资，不出现在结果中\n\n"
            "返回：department_name, employee_name, salary\n"
            "排序：department_name ASC, employee_name ASC"
        ),
        "difficulty": "medium",
        "sample_input": "无",
        "sample_output": "Tech | B | 90\nTech | C | 90",
        "create_table_sql": (
            "CREATE TABLE Departments (\n"
            "    department_id INT PRIMARY KEY,\n"
            "    department_name VARCHAR(50) NOT NULL\n"
            ");\n"
            "CREATE TABLE Employees (\n"
            "    employee_id INT PRIMARY KEY,\n"
            "    employee_name VARCHAR(50) NOT NULL,\n"
            "    department_id INT NOT NULL,\n"
            "    salary INT NOT NULL\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "WITH ranked AS (\n"
                "    SELECT\n"
                "        e.employee_name, e.department_id, e.salary,\n"
                "        DENSE_RANK() OVER (\n"
                "            PARTITION BY e.department_id ORDER BY e.salary DESC\n"
                "        ) AS rk\n"
                "    FROM Employees e\n"
                ")\n"
                "SELECT d.department_name, r.employee_name, r.salary\n"
                "FROM ranked r\n"
                "JOIN Departments d ON r.department_id = d.department_id\n"
                "WHERE r.rk = 2\n"
                "ORDER BY d.department_name, r.employee_name;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Departments (department_id, department_name) VALUES (1, 'Tech'), (2, 'Sales');"
                    "INSERT INTO Employees (employee_id, employee_name, department_id, salary) VALUES "
                    "(1, 'A', 1, 100), (2, 'B', 1, 90), (3, 'C', 1, 90), (4, 'D', 2, 200);"
                ),
                "expected_output": "department_name|employee_name|salary\nTech|B|90\nTech|C|90"
            }
        ],
    },
    # ========== 第 7 题：订单转化漏斗分析 ==========
    {
        "title": "订单转化漏斗分析",
        "description": (
            "## 订单转化漏斗分析\n\n"
            "表 `Events`：user_id, product_id, event_type, event_time\n"
            "事件类型：visit（访问）、add_cart（加购）、pay（支付）\n\n"
            "按 product_id 统计：\n"
            "- visit_users, add_cart_users, pay_users（去重用户数）\n"
            "- visit_to_cart_rate = add_cart_users / visit_users\n"
            "- cart_to_pay_rate = pay_users / add_cart_users\n"
            "- 分母为 0 时转化率记为 0.00\n"
            "- 转化率保留 2 位小数\n\n"
            "排序：product_id ASC"
        ),
        "difficulty": "hard",
        "sample_input": "无",
        "sample_output": "101 | 2 | 1 | 0 | 0.50 | 0.00\n102 | 1 | 0 | 0 | 0.00 | 0.00",
        "create_table_sql": (
            "CREATE TABLE Events (\n"
            "    user_id INT NOT NULL,\n"
            "    product_id INT NOT NULL,\n"
            "    event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('visit','add_cart','pay')),\n"
            "    event_time TIMESTAMP NOT NULL\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "WITH summary AS (\n"
                "    SELECT\n"
                "        product_id,\n"
                "        COUNT(DISTINCT CASE WHEN event_type = 'visit' THEN user_id END) AS visit_users,\n"
                "        COUNT(DISTINCT CASE WHEN event_type = 'add_cart' THEN user_id END) AS add_cart_users,\n"
                "        COUNT(DISTINCT CASE WHEN event_type = 'pay' THEN user_id END) AS pay_users\n"
                "    FROM Events\n"
                "    GROUP BY product_id\n"
                ")\n"
                "SELECT\n"
                "    product_id, visit_users, add_cart_users, pay_users,\n"
                "    ROUND(CASE WHEN visit_users = 0 THEN 0 ELSE add_cart_users::decimal / visit_users END, 2) AS visit_to_cart_rate,\n"
                "    ROUND(CASE WHEN add_cart_users = 0 THEN 0 ELSE pay_users::decimal / add_cart_users END, 2) AS cart_to_pay_rate\n"
                "FROM summary\n"
                "ORDER BY product_id;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Events (user_id, product_id, event_type, event_time) VALUES "
                    "(1, 101, 'visit', now()), (1, 101, 'add_cart', now()), "
                    "(2, 101, 'visit', now()), (1, 102, 'visit', now());"
                ),
                "expected_output": (
                    "product_id|visit_users|add_cart_users|pay_users|visit_to_cart_rate|cart_to_pay_rate\n"
                    "101|2|1|0|0.50|0.00\n"
                    "102|1|0|0|0.00|0.00"
                )
            }
        ],
    },
    # ========== 第 8 题：连续三个月消费增长的用户 ==========
    {
        "title": "连续三个月消费增长的用户",
        "description": (
            "## 连续三个月消费增长的用户\n\n"
            "表 `Users`：user_id (PK), user_name\n"
            "表 `Orders`：order_id (PK), user_id (FK), amount, order_date\n\n"
            "先按 用户+月份 汇总月消费总额，再判断是否存在连续 3 个月的消费总额严格递增。\n"
            "- 月份必须连续（中间不能缺失某月）\n"
            "- 严格递增：m1 < m2 < m3\n\n"
            "返回：user_id, user_name\n"
            "排序：user_id ASC"
        ),
        "difficulty": "hard",
        "sample_input": "无",
        "sample_output": "1 | Alice",
        "create_table_sql": (
            "CREATE TABLE Users (\n"
            "    user_id INT PRIMARY KEY,\n"
            "    user_name VARCHAR(50) NOT NULL\n"
            ");\n"
            "CREATE TABLE Orders (\n"
            "    order_id INT PRIMARY KEY,\n"
            "    user_id INT NOT NULL,\n"
            "    amount DECIMAL(10,2) NOT NULL,\n"
            "    order_date DATE NOT NULL\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "WITH monthly AS (\n"
                "    SELECT\n"
                "        user_id,\n"
                "        DATE_TRUNC('month', order_date) AS month_start,\n"
                "        SUM(amount) AS total_amount\n"
                "    FROM Orders\n"
                "    GROUP BY user_id, DATE_TRUNC('month', order_date)\n"
                "),\n"
                "seq AS (\n"
                "    SELECT\n"
                "        user_id, month_start, total_amount,\n"
                "        LEAD(month_start, 1) OVER w AS next_month,\n"
                "        LEAD(month_start, 2) OVER w AS next_2_month,\n"
                "        LEAD(total_amount, 1) OVER w AS next_amount,\n"
                "        LEAD(total_amount, 2) OVER w AS next_2_amount\n"
                "    FROM monthly\n"
                "    WINDOW w AS (PARTITION BY user_id ORDER BY month_start)\n"
                ")\n"
                "SELECT DISTINCT u.user_id, u.user_name\n"
                "FROM seq s\n"
                "JOIN Users u ON s.user_id = u.user_id\n"
                "WHERE\n"
                "    (EXTRACT(YEAR FROM next_month) * 12 + EXTRACT(MONTH FROM next_month)) - \n"
                "    (EXTRACT(YEAR FROM s.month_start) * 12 + EXTRACT(MONTH FROM s.month_start)) = 1\n"
                "    AND\n"
                "    (EXTRACT(YEAR FROM next_2_month) * 12 + EXTRACT(MONTH FROM next_2_month)) - \n"
                "    (EXTRACT(YEAR FROM next_month) * 12 + EXTRACT(MONTH FROM next_month)) = 1\n"
                "    AND total_amount < next_amount\n"
                "    AND next_amount < next_2_amount\n"
                "ORDER BY u.user_id;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Users (user_id, user_name) VALUES (1, 'Alice'), (2, 'Bob');"
                    "INSERT INTO Orders (order_id, user_id, amount, order_date) VALUES "
                    "(1, 1, 100, '2025-01-05'), (2, 1, 200, '2025-02-10'), (3, 1, 300, '2025-03-15'), "
                    "(4, 2, 100, '2025-01-05'), (5, 2, 100, '2025-02-10'), (6, 2, 100, '2025-03-15');"  # Bob 持平，非递增
                ),
                "expected_output": "user_id|user_name\n1|Alice"
            }
        ],
    },
    # ========== 第 9 题：论坛热帖 ==========
    {
        "title": "论坛热帖",
        "description": (
            "## 论坛热帖\n\n"
            "表 `Posts`：post_id (PK), author_name, reply_to, likes\n"
            "- reply_to 为 NULL 表示原创首发帖子\n"
            "- reply_to 不为 NULL 表示回复某帖子\n\n"
            "找出所有「热点原贴」：\n"
            "- 必须是原创帖子（reply_to IS NULL）\n"
            "- 至少有一个其他帖子直接回复了它\n"
            "- 统计跟帖数量 reply_count\n"
            "- 统计跟帖的平均点赞数 avg_likes（四舍五入到整数）\n\n"
            "返回：post_id, author_name, reply_count, avg_likes\n"
            "排序：post_id ASC"
        ),
        "difficulty": "easy",
        "sample_input": "无",
        "sample_output": "1 | Alice | 2 | 6",
        "create_table_sql": (
            "CREATE TABLE Posts (\n"
            "    post_id INT PRIMARY KEY,\n"
            "    author_name VARCHAR(255),\n"
            "    reply_to INT,\n"
            "    likes INT\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "SELECT\n"
                "    p1.post_id,\n"
                "    p1.author_name,\n"
                "    COUNT(p2.post_id) AS reply_count,\n"
                "    ROUND(AVG(p2.likes)) AS avg_likes\n"
                "FROM Posts p1\n"
                "JOIN Posts p2 ON p1.post_id = p2.reply_to\n"
                "WHERE p1.reply_to IS NULL\n"
                "GROUP BY p1.post_id, p1.author_name\n"
                "ORDER BY p1.post_id;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Posts (post_id, author_name, reply_to, likes) VALUES "
                    "(1, 'Alice', NULL, 10), (2, 'Bob', 1, 5), (3, 'Charlie', 1, 7), "
                    "(4, 'David', NULL, 20);"   # 无回复的原贴，不应出现
                ),
                "expected_output": "post_id|author_name|reply_count|avg_likes\n1|Alice|2|6"
            }
        ],
    },
    # ========== 第 10 题：社区活跃度 ==========
    {
        "title": "社区活跃度",
        "description": (
            "## 社区活跃度\n\n"
            "表 `Activity`：id (PK), user_id, session_id, activity_date, activity_type\n"
            "activity_type：open_session, end_session, scroll_down, send_message\n\n"
            "活跃权重：\n"
            "- open_session → 1 分\n"
            "- scroll_down → 2 分\n"
            "- send_message → 5 分\n"
            "- end_session → 0 分\n\n"
            "统计 2019-06-28 至 2019-07-27（近30天）每天的活跃热度（权重之和）。\n"
            "- 热度为 0 的日期不返回\n"
            "- 按热度降序排列\n\n"
            "返回：daily_heat, activity_date\n"
            "排序：daily_heat DESC"
        ),
        "difficulty": "easy",
        "sample_input": "无",
        "sample_output": "5 | 2019-06-29\n3 | 2019-06-28",
        "create_table_sql": (
            "CREATE TABLE Activity (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    user_id INT,\n"
            "    session_id INT,\n"
            "    activity_date DATE,\n"
            "    activity_type VARCHAR(50) CHECK (activity_type IN ('open_session', 'end_session', 'scroll_down', 'send_message'))\n"
            ");"
        ),
        "answers": [
            {"correct_sql": (
                "SELECT\n"
                "    activity_date,\n"
                "    SUM(\n"
                "        CASE activity_type\n"
                "            WHEN 'open_session' THEN 1\n"
                "            WHEN 'scroll_down' THEN 2\n"
                "            WHEN 'send_message' THEN 5\n"
                "            WHEN 'end_session' THEN 0\n"
                "            ELSE 0\n"
                "        END\n"
                "    ) AS daily_heat\n"
                "FROM Activity\n"
                "WHERE activity_date BETWEEN '2019-06-28' AND '2019-07-27'\n"
                "GROUP BY activity_date\n"
                "HAVING SUM(\n"
                "        CASE activity_type\n"
                "            WHEN 'open_session' THEN 1\n"
                "            WHEN 'scroll_down' THEN 2\n"
                "            WHEN 'send_message' THEN 5\n"
                "            WHEN 'end_session' THEN 0\n"
                "            ELSE 0\n"
                "        END\n"
                "    ) > 0\n"
                "ORDER BY daily_heat DESC;"
            )}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO Activity (user_id, session_id, activity_date, activity_type) VALUES "
                    "(1, 1, '2019-06-28', 'open_session'), (1, 1, '2019-06-28', 'scroll_down'), "
                    "(2, 2, '2019-06-29', 'send_message');"
                ),
                "expected_output": "activity_date|daily_heat\n2019-06-29|5\n2019-06-28|3"
            }
        ],
    },
    # ========== 第 11 题：简单查询练习 ==========
    {
        "title": "简单查询练习",
        "description": (
            "## 简单查询练习\n\n"
            "表 `employees`：\n"
            "| Column Name | Type |\n"
            "|---|---|\n"
            "| id | SERIAL (PK) |\n"
            "| name | VARCHAR(50) |\n"
            "| age | INT |\n\n"
            "查询所有员工的姓名和年龄，不需要排序。\n\n"
            "返回列：name, age"
        ),
        "difficulty": "easy",
        "sample_input": "无",
        "sample_output": "Alice | 30\nBob | 25",
        "create_table_sql": (
            "CREATE TABLE employees (\n"
            "    id SERIAL PRIMARY KEY,\n"
            "    name VARCHAR(50),\n"
            "    age INT\n"
            ");"
        ),
        "answers": [
            {"correct_sql": "SELECT name, age FROM employees;"}
        ],
        "test_cases": [
            {
                "test_input": (
                    "INSERT INTO employees (id, name, age) VALUES (1, 'Alice', 30), (2, 'Bob', 25);"
                ),
                "expected_output": "name|age\nAlice|30\nBob|25"
            }
        ],
    },
]

class Command(BaseCommand):
    help = '导入上机课 11 道题目到数据库（含全面测试用例）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace', action='store_true',
            help='覆盖模式：先删除同名题目再重新导入（默认跳过已存在的同名题目）'
        )
        parser.add_argument(
            '--teacher-id', type=int, default=1,
            help='教师用户 ID（默认为 1）'
        )

    def handle(self, *args, **options):
        teacher_id = options['teacher_id']
        replace = options['replace']
        try:
            teacher = User.objects.get(id=teacher_id, user_type='teacher')
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f'教师用户 ID={teacher_id} 不存在。请先注册一个教师账号。\n'
                f'用法: curl -X POST http://127.0.0.1:8000/api/auth/register/ '
                f'-H "Content-Type: application/json" '
                f'-d \'{{"username":"teacher","email":"t@t.com","password":"123456","user_type":"teacher"}}\''
            ))
            return

        # 可选：清空旧数据
        # Question.objects.all().delete()

        created = 0
        skipped = 0
        for item in QUESTIONS:
            q_data = dict(item)
            answers = q_data.pop('answers', [])
            test_cases = q_data.pop('test_cases', [])

            # 幂等：同名题目已存在时默认跳过，避免重复导入
            existing = Question.objects.filter(title=q_data.get('title'))
            if existing.exists():
                if not replace:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(
                        f'  ⏭  已存在，跳过：{q_data.get("title")}'
                    ))
                    continue
                existing.delete()

            question = Question.objects.create(teacher=teacher, **q_data)
            for ans in answers:
                Answer.objects.create(question=question, **ans)
            for tc in test_cases:
                TestCase.objects.create(question=question, **tc)

            created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  ✅ [{q_data["difficulty"]}] {q_data["title"]}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'\n🎉 成功导入 {created} 道题目' + (f'，跳过 {skipped} 道已存在的题目' if skipped else '') + '！'
        ))