# Java 集合框架

## HashMap
HashMap 是基于哈希表的 Map 接口实现，允许 null 键和 null 值。
线程不安全，初始容量 16，加载因子 0.75。
扩容时容量翻倍，使用头插法（JDK 1.7+ 改为尾插法）。

## ConcurrentHashMap
ConcurrentHashMap 是线程安全的 Map 实现。
JDK 1.7 及之前使用分段锁，JDK 1.8 改为 CAS + synchronized。
不允许 null 键和 null 值。

# Spring 框架

## Spring Boot
Spring Boot 是简化 Spring 应用开发的框架。
提供自动配置、内嵌服务器、起步依赖等特性。