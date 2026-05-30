package storage

import (
	"database/sql"
	"fmt"
	"net"
	"net/url"
	"strings"

	_ "github.com/go-sql-driver/mysql"
)

func OpenMySQL(databaseURL string) (*sql.DB, error) {
	if strings.TrimSpace(databaseURL) == "" {
		return nil, fmt.Errorf("APP_DATABASE_URL 不能为空")
	}

	parsed, err := url.Parse(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("解析 APP_DATABASE_URL 失败: %w", err)
	}
	if parsed.Scheme != "mysql" {
		return nil, fmt.Errorf("仅支持 mysql:// 连接串")
	}

	username := parsed.User.Username()
	password, _ := parsed.User.Password()
	host := parsed.Hostname()
	port := parsed.Port()
	if port == "" {
		port = "3306"
	}
	databaseName := strings.TrimPrefix(parsed.Path, "/")
	if databaseName == "" {
		return nil, fmt.Errorf("数据库名不能为空")
	}

	query := parsed.Query()
	if query.Get("charset") == "" {
		query.Set("charset", "utf8mb4")
	}
	query.Set("parseTime", "true")
	query.Set("loc", "Local")
	query.Set("multiStatements", "true")

	dsn := fmt.Sprintf(
		"%s:%s@tcp(%s)/%s?%s",
		username,
		password,
		net.JoinHostPort(host, port),
		databaseName,
		query.Encode(),
	)

	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, fmt.Errorf("打开 MySQL 连接失败: %w", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	return db, nil
}
