/** DDL 出题模板：一键填充「题目描述 + 参考 DDL（+ 前置语句）」。 */
export interface DdlTemplate {
  id: string
  label: string
  description: string
  reference_sql: string
  setup_sql?: string
}

export const DDL_TEMPLATES: DdlTemplate[] = [
  {
    id: 'create-table-basic',
    label: '建表：自增主键 + 非空 + 唯一',
    description:
      '创建 users 表：id 为自增整数主键；username 为长度 50 的非空字符串且唯一；'
      + 'created_at 为非空时间戳，默认当前时间。',
    reference_sql:
      'CREATE TABLE users (\n'
      + '    id SERIAL PRIMARY KEY,\n'
      + '    username VARCHAR(50) NOT NULL UNIQUE,\n'
      + '    created_at TIMESTAMP NOT NULL DEFAULT now()\n'
      + ');',
  },
  {
    id: 'check-range',
    label: '约束：CHECK 取值范围',
    description:
      '创建 ratings 表：id 自增主键；score 为非空整数，取值必须在 1 到 5 之间。',
    reference_sql:
      'CREATE TABLE ratings (\n'
      + '    id SERIAL PRIMARY KEY,\n'
      + '    score INTEGER NOT NULL,\n'
      + '    CONSTRAINT rating_range CHECK (score BETWEEN 1 AND 5)\n'
      + ');',
  },
  {
    id: 'foreign-key',
    label: '关系：外键（级联删除）',
    description:
      '创建 authors 表（id 自增主键，name 长度 50 非空）与 books 表'
      + '（id 自增主键，title 长度 200 非空，author_id 非空整数外键指向 authors.id，'
      + '删除作者时级联删除其图书）。',
    reference_sql:
      'CREATE TABLE authors (\n'
      + '    id SERIAL PRIMARY KEY,\n'
      + '    name VARCHAR(50) NOT NULL\n'
      + ');\n'
      + 'CREATE TABLE books (\n'
      + '    id SERIAL PRIMARY KEY,\n'
      + '    title VARCHAR(200) NOT NULL,\n'
      + '    author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE\n'
      + ');',
  },
  {
    id: 'alter-add-constraint',
    label: 'ALTER：加唯一约束',
    description:
      '已有 members 表（id 自增主键，email 长度 100 的非空字符串）。'
      + '为 email 添加唯一约束（约束名 uq_members_email）。',
    setup_sql:
      'CREATE TABLE members (\n'
      + '    id SERIAL PRIMARY KEY,\n'
      + '    email VARCHAR(100) NOT NULL\n'
      + ');',
    reference_sql: 'ALTER TABLE members ADD CONSTRAINT uq_members_email UNIQUE (email);',
  },
  {
    id: 'unique-index',
    label: '索引：唯一索引',
    description:
      '已有 users_idx 表（id 自增主键，email 长度 100 非空）。'
      + '创建唯一索引 uq_users_idx_email，保证 email 不重复。',
    setup_sql:
      'CREATE TABLE users_idx (\n'
      + '    id SERIAL PRIMARY KEY,\n'
      + '    email VARCHAR(100) NOT NULL\n'
      + ');',
    reference_sql: 'CREATE UNIQUE INDEX uq_users_idx_email ON users_idx (email);',
  },
]
