-- Runs automatically on first container start via /docker-entrypoint-initdb.d
-- (official mysql/mariadb images execute *.sql files here on an empty data dir)
CREATE DATABASE IF NOT EXISTS tododb;
CREATE USER IF NOT EXISTS 'todo'@'%' IDENTIFIED BY 'todopass';
GRANT ALL PRIVILEGES ON tododb.* TO 'todo'@'%';
FLUSH PRIVILEGES;
