-- 判题容器初始化脚本：tmpfs 使数据目录每次重建都会重新 initdb，本脚本随之重新执行。
-- 1) 将 public schema 所有权转移给不可登录角色，判题账号将无法访问/删除 public；
-- 2) 收敛判题账号权限（current_user 即 POSTGRES_USER，去掉 SUPERUSER/CREATEDB/CREATEROLE）。
CREATE ROLE schema_owner NOLOGIN;
ALTER SCHEMA public OWNER TO schema_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER ROLE current_user NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
