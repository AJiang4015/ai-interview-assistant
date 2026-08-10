# spring

### 你对 Spring 的理解

Spring 的本质是一个“运行时可管理的对象工厂 + 面向切面系统”。

它统一管理对象的生命周期，并在对象之间织入各种能力，从而让业务开发者专注业务。

换一种更架构味的说法：

Spring = IoC 容器（对象管理系统） + AOP（行为增强系统） + 生态整合框架

### spring的核心思想说说你的理解？

IoC 和 AOP。

IoC 提供了一个容器化的对象管理机制，让对象不再自行创建依赖，而是由容器统一控制和装配。AOP 将横切逻辑从业务中分离，通过代理机制在方法前后织入行为，保持代码单一职责。借助 IoC 的依赖图和 AOP 的增强机制，Spring 可以在 Bean 生命周期的任意阶段插入扩展点，因此形成了一个高度可扩展的基础设施平台，使得事务、缓存、安全、MVC、Boot 等能力都能以插件的方式集成进来。Spring 的本质是一个以 IoC 为核心的可扩展平台，而不是一个简单框架。  

### Spring的IoC介绍一下

Spring IoC（控制反转）是 Spring 框架的核心。它是一个管理应用中对象（在 Spring 中称为 Bean）及其依赖关系的容器。

- **容器（IoC Container）**：BeanFactory 和 ApplicationContext 是 IoC 容器的两个主要接口。ApplicationContext 是 BeanFactory 的超集，提供了更丰富的功能（如国际化、事件发布等），是我们在开发中最常用的。
- **Bean**：被 Spring IoC 容器管理的对象就是 Bean。
- **依赖注入（DI - Dependency Injection）**：IoC 是一种思想，而 DI 是实现 IoC 的一种具体模式。Spring 通过 DI 来实现对象依赖关系的装配。当一个 Bean 需要另一个 Bean 时，容器会自动将后者“注入”到前者中。

**注入方式主要有三种**：

1. **构造器注入**：通过构造函数的参数注入依赖。（官方推荐，可以保证对象在创建时就是完整的）
2. **Setter 注入**：通过 setter 方法注入依赖。
3. **字段注入**：直接在字段上使用 @Autowired 注解。（代码最简洁，但有一定缺点，如不利于单元测试）

### Spring的AOP介绍一下

Spring AOP（面向切面编程）是 Spring 框架的另一个核心。它允许开发者定义“横切关注点”，并将它们与业务逻辑分离。

**AOP 核心概念**：

- **切面（Aspect）**：一个模块，封装了特定的横切关注点（如日志切面、事务切面）。
- **连接点（Join Point）**：程序执行过程中的一个点，例如方法的调用或异常的抛出。在 Spring AOP 中，连接点总是**方法的执行**。
- **通知（Advice）**：切面在特定连接点上执行的**动作**。主要有五种类型：

- @Before：前置通知，在方法执行前。
- @After：后置通知，在方法执行后（无论成功还是异常）。
- @AfterReturning：返回通知，在方法成功执行并返回后。
- @AfterThrowing：异常通知，在方法抛出异常后。
- @Around：环绕通知，最强大的通知，可以控制方法的执行（是否执行、修改返回值等）。

- **切点（Pointcut）**：一个**表达式**，用于匹配一组连接点。通知会作用在所有匹配的切点上。
- **目标对象（Target Object）**：被一个或多个切面所通知的对象。
- **代理（Proxy）**：AOP 框架创建的对象，它封装了目标对象，并织入了切面逻辑。客户端调用的实际上是代理对象。

### IOC和AOP是通过什么机制来实现的？

- **IOC 实现原理**

1. Spring 容器启动，解析配置（XML/注解/扫描）。
2. 根据 BeanDefinition 解析类信息（class、scope、构造方法、依赖等）。
3. 通过反射创建对象（构造注入和 set 注入都支持）。
4. 把 Bean 存到单例池（一级缓存）。
5. 自动注入（Autowired）——反射注入字段、构造器注入。
6. 调用 BeanPostProcessor 执行前置/后置增强（AOP、@Autowired 都在这里实现）。

**关键机制：反射 + BeanDefinition + 单例池 + BeanPostProcessor**

- **AOP 的实现机制**：**动态代理 (Dynamic Proxy)**。	

1. Spring AOP 在运行时，不会修改目标对象的源代码。
2. 而是为目标对象创建一个**代理对象**。这个代理对象“包裹”了原始对象。
3. 当客户端调用代理对象的方法时，代理对象会在调用原始对象的**方法前后**，插入切面逻辑（即各种通知）。
4. Spring AOP 主要使用两种动态代理技术：

- **JDK 动态代理**：要求目标类必须**实现一个或多个接口**。Spring 会创建一个实现了相同接口的代理类。
- **CGLIB 代理**：如果目标类**没有实现接口**，Spring 会使用 CGLIB。它通过**创建目标类的子类**作为代理，并重写父类的方法来实现。



### 依赖倒置，依赖注入，控制反转分别是什么？

- **依赖倒置原则（DIP）**：是一种**设计原则**。它倡导：

- 高层模块不应该依赖于低层模块，两者都应该依赖于**抽象**。
- 抽象不应该依赖于细节，细节应该依赖于抽象。

- **控制反转（IoC）**：是一种**设计模式**，是实现依赖倒置原则的一种**思想框架**。它把创建和管理依赖对象的控制权从代码中移交给了外部容器。
- **依赖注入（DI）**：是实现控制反转（IoC）的**一种具体技术手段**。它是“反转”这个思想的实际动作，即由容器在运行时动态地将依赖关系注入到组件中。

**关系总结**：

- **DIP 是目标**
- **IoC 是实现该目标的模式**。
- **DI 是实现该模式的具体方法**。

### 依赖注入（DI）了解吗？怎么实现依赖注入的？

依赖注入（DI）就是由 Spring 容器在创建 Bean 的过程中，将它所依赖的其它 Bean 自动注入到其属性或构造方法参数中的过程。

**Spring 实现 DI 的主要方式**：

1. 基于构造器注入
2. setter 方法注入
3. 注解注入

### 如果让你设计一个SpringIoC，你觉得会从哪些方面考虑这个设计？

这是一个非常好的开放性问题，考察的是对 IoC 原理的深度理解。我会这样设计：

1. **配置解析模块**：

- 定义一种方式来让用户告诉我的 IoC 容器要管理哪些 Bean。可以是 XML 文件、注解，或者 Java 配置类。
- 需要一个**配置解析器**，能读取这些配置，并将其转换成一种统一的内部数据结构。

1. **Bean 定义注册模块**：

- 设计一个 BeanDefinition 类，用来存储解析到的 Bean 的元数据，如：类名（className）、是否单例（scope）、构造函数参数、属性依赖等。
- 需要一个**注册表（Registry）**，通常是一个 Map<String, BeanDefinition>，用来存储所有 Bean 的定义。

1. **Bean 实例化与生命周期管理模块**：

- 这是核心。提供一个 getBean(String beanName) 方法。
- **实例化**：当调用 getBean 时，首先检查缓存中是否已存在该 Bean 的实例（针对单例）。如果没有，就从注册表中获取 BeanDefinition，然后使用**反射**来创建实例。
- **依赖注入**：实例创建后，再次检查 BeanDefinition，找出它的依赖。递归调用 getBean 来获取依赖的实例，然后通过**反射**将其注入到当前实例的字段或 setter 方法中。
- **缓存**：设计一个单例缓存池，通常是 Map<String, Object>，用于存放已经创建好的单例 Bean，避免重复创建。
- **生命周期回调**：提供扩展点，允许用户在 Bean 初始化前后、销毁前执行自定义逻辑（类似 BeanPostProcessor 和 init-method）。

1. **容器本身**：

- 设计一个顶层的容器接口，如 ApplicationContext，它整合了以上所有模块，对外提供统一的 getBean 方法。

### SpringAOP主要想解决什么问题

主要解决**代码逻辑的解耦**，将那些与核心业务无关，但又在多个模块中重复出现的**横切关注点（Cross-cutting Concerns）**分离出来。

**典型问题场景**：

- **日志记录**：每个方法的开始和结束都需要打日志。
- **事务管理**：很多数据库操作方法都需要放在一个事务中。
- **权限控制**：许多方法在执行前需要检查用户是否有权限。
- **性能监控**：需要统计每个方法的执行时间。

如果不使用 AOP，这些代码会散落在各个业务类中，导致：

- **代码冗余**。
- **核心业务逻辑被污染**，不易阅读和维护。
- **修改困难**，比如想改变日志格式，需要修改所有地方。

AOP 通过将这些通用功能集中到一个“切面”中，让业务类保持纯净，极大地提高了代码的模块化程度和可维护性。

### AOP在spring中的应用，你知道哪些？

1. **声明式事务管理**：这是 AOP 最经典的应用。通过 @Transactional 注解，Spring AOP 会自动为方法添加事务管理逻辑（开启事务、提交或回滚）。你完全不需要写 try-catch-finally 的事务管理代码。
2. **Spring Security**：用于进行权限控制。AOP 在方法执行前检查用户是否拥有所需权限。
3. **异步处理**：通过 @Async 注解，AOP 会将方法的调用放入一个线程池中异步执行。
4. **缓存**：Spring 的缓存抽象（@Cacheable, @CacheEvict等）也是通过 AOP 实现的，在方法执行前后进行缓存的读取和更新。
5. **日志记录和性能监控**：开发者可以自定义切面来实现这些功能。



### 动态代理是什么？

动态代理是一种在**运行时**动态创建代理对象的技术。你不需要手动编写代理类，代理类是在程序运行时由 JVM 根据你的需要动态生成的。

### 动态代理和静态代理的区别

| **特性**     | **静态代理**                                                 | **动态代理**                                                 |
| ------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **创建时机** | **编译时**。代理类的 .java 文件是手写的，编译后生成 .class 文件。 | **运行时**。代理类是在内存中动态生成的，没有 .java 源文件。  |
| **灵活性**   | **低**。一个代理类只能为一个接口服务。如果要代理多个接口，需要写多个代理类。 | **高**。一个代理处理器（InvocationHandler）可以为任意类型的接口服务。 |
| **代码量**   | **大**。每个被代理的类都需要一个对应的代理类，导致类数量翻倍。 | **小**。只需要一个统一的代理逻辑处理器。                     |
| **典型代表** | 传统的设计模式中的代理模式。                                 | Spring AOP, RPC 框架的客户端 Stub。                          |

### 能使用静态代理的方式实现AOP吗？

**理论上可以，但实践中不可行，因为它违背了 AOP 的初衷。**

AOP 的目标是无侵入地、动态地将通用逻辑应用到大量类上。如果使用静态代理：

1. **工作量巨大**：你需要为每一个需要被增强的类手动编写一个代理类。
2. **灵活性差**：如果切面逻辑发生变化，需要修改所有的静态代理类。
3. **无法动态应用**：无法根据配置在运行时决定是否应用切面。

所以，AOP 必须依赖**动态代理**这种在运行时生成代理对象的技术，才能实现其灵活、强大的功能。

### AOP实现有哪些注解？

- @Aspect：声明一个类为切面。
- @Pointcut：定义一个切点表达式，指定通知应该作用于哪些方法。
- @Before：前置通知。
- @After：后置通知。
- @AfterReturning：返回通知。
- @AfterThrowing：异常通知。
- @Around：环绕通知。



# Spring 循环依赖

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764132544536-0ef6e1c1-37ab-4ce9-aa08-927096f7685f.png)

 Spring 的循环依赖解决依赖于“三级缓存 + 提前暴露半成品 bean”。
只有在构造方法执行之后才能获取到“半成品对象”，因此 setter 注入和字段注入可以解决循环依赖，但构造器注入无法生成半成品对象，所以无法解决循环依赖。  

### Spring是如何解决循环依赖的？

Spring 只解决了**单例 Bean 的、基于字段注入（或 setter 注入）的循环依赖**。构造器注入的循环依赖无法解决。

**核心思想**：**提前暴露（Early Exposure）**。

一个 Bean 的创建过程可以分为两步：

1. **实例化**：调用构造函数，创建出一个“原始”的 Bean 对象。
2. **属性填充**：为这个原始对象的字段注入依赖。

Spring 解决循环依赖的关键在于，它不等到 Bean 完全创建好（实例化 + 属性填充）之后才将其放入缓存，而是在**第一步（实例化）刚完成**，就将这个“半成品”的 Bean 对象**提前暴露**出去，放到一个特殊的缓存中。

**流程（以 A 依赖 B，B 依赖 A 为例）**：

```css
getBean(A)
├─ new A()
├─ A 的 ObjectFactory → 放三级缓存
├─ A 注入属性：需要 B → getBean(B)
│     ├─ new B()
│     ├─ B 的 ObjectFactory → 放三级缓存
│     ├─ B 注入属性：需要 A → getBean(A)
│     │     ├─ 一级：无
│     │     ├─ 二级：无
│     │     ├─ 三级：有 → ObjectFactory.getObject()
│     │     │     └─ earlyA → 放入二级缓存，删三级缓存
│     │     └─ 返回 earlyA（半成品A）
│     ├─ B 完成初始化 → 放入一级缓存
│     └─ 返回完整B
├─ A 注入属性：找到 B（一级缓存）
├─ A 完成初始化 → 放入一级缓存
└─ 删除 A 的二级缓存引用
```



### Spring为什么用3级缓存解决循环依赖问题？用2级缓存不行吗？

- 循环依赖时，Spring先创建的是**实例对象**（半成品，放二级缓存），保证依赖链能断开，不会死循环。
- 后续如果这个Bean需要被AOP增强（比如事务、日志等），Spring会用三级缓存里的工厂去创建**代理对象**，代理对象包裹了这个实例，增强了功能。
- 最终暴露给外部用的就是**代理对象**，而不是直接的实例。

“让原始对象用于解决循环依赖”“让代理对象用于最终增强”“并且让两者互不冲突”

**如果不存在 AOP（即不需要创建代理对象），二级缓存是完全可以的。**

**为什么需要三级缓存？关键是为了解决 AOP 代理问题。**

- **问题**：循环依赖中，注入给其他对象的 Bean 必须是**最终的代理对象**，而不是原始对象，否则 AOP 会失效。但 Spring 在创建 Bean 的早期，并不知道它未来是否需要被 AOP 代理。
- **如果用二级缓存**：

1. 创建 A 的原始对象后，是直接把**原始对象**放入二级缓存吗？
2. 如果是，那么当 B 依赖 A 时，它从二级缓存拿到的是**原始的 A**。如果 A 恰好需要被代理，那么 B 持有的就不是代理对象，AOP 就失效了。
3. 那我们能不能一创建 A 的原始对象，就立刻判断是否需要代理，然后把**代理对象**放入二级缓存？也不行，因为这违背了 Spring 的设计，Bean 的代理创建应该在 BeanPostProcessor（生命周期的后期）中进行。

- **三级缓存的巧妙之处**：

1. 三级缓存 singletonFactories 中存的不是对象，而是一个**工厂（**ObjectFactory）。
2. 这个工厂的 getObject() 方法被设计为：**当我被调用时，我才去判断是否需要创建代理，并返回最终的对象（可能是原始对象，也可能是代理对象）。**
3. 这样，就把**“创建代理”这个动作推迟到了真正发生依赖注入的时候**。
4. 当 B 依赖 A 时，它从三级缓存中获取 A 的工厂，调用 getObject()，此时 AOP 的逻辑介入，判断 A 是否需要代理，如果需要，就创建并返回代理 A，如果不需要，就返回原始 A。问题完美解决。

**总结**：二级缓存存的是**对象**，三级缓存存的是**工厂**。三级缓存的引入是为了**推迟代理对象的创建时机**，从而在循环依赖的场景下，也能正确地处理 AOP。

Spring 在遇到循环依赖时从三级缓存拿到工厂 ObjectFactory

调用，内部会执行 **SmartInstantiationAwareBeanPostProcessor** 的：

```plain
earlyBean = getEarlyBeanReference(beanName, rawBean);
```

例如 AOP 会在这里：

✔️ 判断该 bean 是否需要代理
✔️ 如果需要 → 创建代理对象
✔️ 如果不需要 → 返回原始对象

二级缓存存放的为前期 Bean（可能为实例也可能为代理）

### spring三级缓存的数据结构是什么？

它们都是 ConcurrentHashMap，保证线程安全。

1. **一级缓存****singletonObjects**：Map<String, Object>

- 存放完全初始化好的**最终单例 Bean**。

1. **二级缓存****earlySingletonObjects**：Map<String, Object>

- 存放**提前暴露的“半成品”Bean**。这些 Bean 已经实例化但未完成属性填充。它的作用是缓存从三级缓存工厂创建出来的对象，避免重复创建。

1. **三级缓存****singletonFactories**：Map<String, ObjectFactory<?>>

- 存放用于创建 Bean 的**工厂对象**。在发生循环依赖时，从这里获取工厂，调用其 getObject() 方法来得到 Bean 实例（可能是代理对象）。

# Spring 事务

### Spring支持的两种事务管理方式

- **编程式事务**

- 使用 Transationtemplate 进行编写，使用.excute() 方法

```plain
@Autowired
private TransactionTemplate transactionTemplate;
public void testTransaction() {
    transactionTemplate.execute(new TransactionCallbackWithoutResult() {
        @Override
        protected void doInTransactionWithoutResult(TransactionStatus transactionStatus) {
            try {

                // ....  业务代码
            } catch (Exception e){
                //回滚
                transactionStatus.setRollbackOnly();
            }

        }
    });
}
```

- 使用 TransationManger 进行管理

```plain
@Autowired
private PlatformTransactionManager transactionManager;

public void testTransaction() {

  TransactionStatus status = transactionManager.getTransaction(new DefaultTransactionDefinition());
          try {
               // ....  业务代码
              transactionManager.commit(status);
          } catch (Exception e) {
              transactionManager.rollback(status);
          }
}
```

- **声明式事务**

- 使用 `@Transational` 注解
- @Transactional(propagation = Propagation.REQUIRED)

### 事务管理接口

Spring 框架中，事务管理相关最重要的 3 个接口如下：

- `PlatformTransactionManager`：（平台）事务管理器，Spring 事务策略的核心。
- `TransactionDefinition`：事务定义信息(事务隔离级别、传播行为、超时、只读、回滚规则)。
- `TransactionStatus`：事务运行状态。

我们可以把 `PlatformTransactionManager` 接口可以被看作是事务上层的管理者，而 `**TransactionDefinition` 和 `TransactionStatus` 这两个接口可以看作是事务的描述。

`PlatformTransactionManager` 会根据 `TransactionDefinition` 的定义比如事务超时时间、隔离级别、传播行为等来进行事务管理 ，而 `TransactionStatus` 接口则提供了一些方法来获取事务相应的状态比如是否新事务、是否可以回滚等等。



### 事务传播行为

**事务传播行为是为了解决业务层方法之间互相调用的事务问题**。

即事务的传播行为是指当前事务方法被另一方法调用，即嵌套调用方式时，事务是如何传播的？

### 七种传播行为

| **事务传播行为类型**      | **说明**                                                     |
| ------------------------- | ------------------------------------------------------------ |
| PROPAGATION_REQUIRED      | 如果当前没有事务，就新建一个事务，如果已经存在一个事务中，加入到这个事务中。这是最常见的选择。 |
| PROPAGATION_SUPPORTS      | 支持当前事务，如果当前没有事务，就以非事务方式执行。         |
| PROPAGATION_MANDATORY     | 使用当前的事务，如果当前没有事务，就抛出异常。               |
| PROPAGATION_REQUIRES_NEW  | 新建事务，如果当前存在事务，把当前事务挂起。                 |
| PROPAGATION_NOT_SUPPORTED | 以非事务方式执行操作，如果当前存在事务，就把当前事务挂起。   |
| PROPAGATION_NEVER         | 以非事务方式执行，如果当前存在事务，则抛出异常。             |
| PROPAGATION_NESTED        | 如果当前存在事务，则在嵌套事务内执行。如果当前没有事务，则执行与PROPAGATION_REQUIRED类似的操作。 |

![img](https://cdn.nlark.com/yuque/0/2025/jpeg/53862437/1764146188425-9647e5e6-37e8-48bf-aab8-795dd72d6ef0.jpeg)



### 事务隔离级别

`TransactionDefinition` 接口中定义了五个表示隔离级别的常量：

```plain
public interface TransactionDefinition {
    ......
    int ISOLATION_DEFAULT = -1;
    int ISOLATION_READ_UNCOMMITTED = 1;
    int ISOLATION_READ_COMMITTED = 2;
    int ISOLATION_REPEATABLE_READ = 4;
    int ISOLATION_SERIALIZABLE = 8;
    ......
}
```

关于 Spring 事务隔离级别与数据库隔离级别优先级

Spring 事务隔离级别 > 数据库隔离级别

### 事务只读属性

多条sql语句全部为查询时开启，多条查询语句在同一事务。

保证了数据读取的一致性。

### 事务回滚规则

默认情况下，事务只有遇到运行期异常（`RuntimeException` 的子类）时才会回滚，`Error` 也会导致事务回滚，但是，在遇到检查型（Checked）异常时不会回滚。

指定异常回滚

@Transactional(rollbackFor= MyException.class)

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764146189219-ba56e650-9ab9-4e33-8857-4b67b2feb026.gif)

### @Transational 注解原理

`@Transactional` -> **Spring AOP 拦截** -> **创建动态代理** (根据有无接口选择 JDK 或 CGLIB) -> **代理对象执行** (在真实方法前后加入事务管理逻辑) -> **调用真实业务方法**。

### 事务失效

1. **方法访问权限**：方法是 public 吗？
2. **调用方式**：是不是类内部 this 调用？
3. **异常处理**：异常被 catch 了吗？抛出的异常类型对吗 (RuntimeException)？
4. **数据库引擎**：MySQL 是 InnoDB 引擎吗？
5. **Spring Bean**：类被 Spring 管理了吗？
6. **传播行为**：子方法的传播行为设置是否正确？

### Spring的事务什么情况下会失效？

1. **方法不是****public****的**：Spring AOP 代理默认只对 public 方法生效。
2. **方法被****final****或****static****修饰**：CGLIB 是通过继承来实现的，final 方法无法被重写，static 方法属于类而不是实例，都无法被代理。
3. **同一个类中的方法调用（\****this** **调用）**：当一个类中的 A 方法调用同一个类的 B 方法（this.B()）时，如果 B 方法有 @Transactional 注解，事务会失效。因为 this 调用的是原始对象的方法，而不是代理对象的方法，从而绕过了 AOP 的事务增强。
4. **异常被****catch****掉了**：如果业务方法内部捕获了异常，并且没有重新抛出，Spring 的事务管理器就感知不到异常，导致事务不会回滚。
5. **抛出的异常类型不正确**：Spring 事务默认只对 RuntimeException 和 Error 类型的异常进行回滚。如果方法抛出的是一个受检异常（Checked Exception，如 IOException），事务不会回滚。可以通过 @Transactional(rollbackFor = Exception.class) 来改变这个行为。
6. **数据库引擎不支持事务**：如 MySQL 的 MyISAM 引擎就不支持事务。
7. **事务传播行为配置错误**：例如，一个需要新事务的方法，被配置为 PROPAGATION_SUPPORTS，它会以非事务方式运行。

### Spring的事务，使用this调用是否生效？

**不生效。**

原因在于 Spring 事务是基于 AOP（动态代理）实现的。

- 容器中获取到的 Bean（如 myService）实际上是一个代理对象。
- 当你从外部调用 myService.methodA() 时，调用的是代理对象的方法，AOP 的事务逻辑可以被执行。
- 但是，如果在 methodA 内部调用 this.methodB()，this 指向的是**原始对象**，而不是代理对象。
- 因此，这次调用是原始对象内部的方法调用，完全绕过了代理，AOP 也就无法介入，methodB 上的 @Transactional 注解自然就失效了。

**解决方法**：

- 注入自己：在类中注入自身的代理对象，然后用代理对象去调用方法。
- 使用 AopContext.currentProxy() 获取当前代理对象。
- 将方法拆分到不同的类中。



# Spring 的 Bean

### Bean 的生命周期

**四大阶段**：实例化 -> 属性填充 -> 初始化 -> 销毁。

初始化的执行顺序

1. 执行Aware相关接口
2. BeanPostProcessor的前置处理
3. 执行初始化方法

1. @PostConstruct注解
2. InitializingBean 接口
3. xml 的 init-method 方法

1. BeanPostProcessor的后置处理（AOP）
2. @PreDestory 标注 销毁前之前的行为
3. `DisposableBean` 和 `destory-method`处理销毁

```java
protected Object doCreateBean(String beanName, RootBeanDefinition mbd, @Nullable Object[] args)
throws BeanCreationException {

    // 
    BeanWrapper instanceWrapper = null;
    if (mbd.isSingleton()) {
        instanceWrapper = this.factoryBeanInstanceCache.remove(beanName);
    }
    if (instanceWrapper == null) {
        // 创建Bean
        instanceWrapper = createBeanInstance(beanName, mbd, args);
    }
    Object bean = instanceWrapper.getWrappedInstance();
    Class<?> beanType = instanceWrapper.getWrappedClass();
    if (beanType != NullBean.class) {
        mbd.resolvedTargetType = beanType;
    }

    // Allow post-processors to modify the merged bean definition.
    synchronized (mbd.postProcessingLock) {
        if (!mbd.postProcessed) {
            try {
                applyMergedBeanDefinitionPostProcessors(mbd, beanType, beanName);
            }
            catch (Throwable ex) {
                throw new BeanCreationException(mbd.getResourceDescription(), beanName,
                                                "Post-processing of merged bean definition failed", ex);
            }
            mbd.postProcessed = true;
        }
    }


    boolean earlySingletonExposure = (mbd.isSingleton() && this.allowCircularReferences &&
                                      isSingletonCurrentlyInCreation(beanName));
    if (earlySingletonExposure) {
        if (logger.isTraceEnabled()) {
            logger.trace("Eagerly caching bean '" + beanName +
                         "' to allow for resolving potential circular references");
        }
        addSingletonFactory(beanName, () -> getEarlyBeanReference(beanName, mbd, bean));
    }

    // Initialize the bean instance.
    Object exposedObject = bean;
    try {
        // Bean属性赋值/填充
        populateBean(beanName, mbd, instanceWrapper);
        // 初始化Bean
        exposedObject = initializeBean(beanName, exposedObject, mbd);
    }
    catch (Throwable ex) {
        if (ex instanceof BeanCreationException && beanName.equals(((BeanCreationException) ex).getBeanName())) {
            throw (BeanCreationException) ex;
        }
        else {
            throw new BeanCreationException(
                mbd.getResourceDescription(), beanName, "Initialization of bean failed", ex);
        }
    }

    if (earlySingletonExposure) {
        Object earlySingletonReference = getSingleton(beanName, false);
        if (earlySingletonReference != null) {
            if (exposedObject == bean) {
                exposedObject = earlySingletonReference;
            }
            else if (!this.allowRawInjectionDespiteWrapping && hasDependentBean(beanName)) {
                String[] dependentBeans = getDependentBeans(beanName);
                Set<String> actualDependentBeans = new LinkedHashSet<>(dependentBeans.length);
                    for (String dependentBean : dependentBeans) {
                        if (!removeSingletonIfCreatedForTypeCheckOnly(dependentBean)) {
                            actualDependentBeans.add(dependentBean);
                        }
                    }
                    if (!actualDependentBeans.isEmpty()) {
                        throw new BeanCurrentlyInCreationException(beanName,
                                "Bean with name '" + beanName + "' has been injected into other beans [" +
                                StringUtils.collectionToCommaDelimitedString(actualDependentBeans) +
                                "] in its raw version as part of a circular reference, but has eventually been " +
                                "wrapped. This means that said other beans do not use the final version of the " +
                                "bean. This is often the result of over-eager type matching - consider using " +
                                "'getBeanNamesForType' with the 'allowEagerInit' flag turned off, for example.");
                    }
                }
            }
        }

        // Register bean as disposable.
        try {
            // 销毁Bean
            registerDisposableBeanIfNecessary(beanName, bean, mbd);
        }
        catch (BeanDefinitionValidationException ex) {
            throw new BeanCreationException(
                    mbd.getResourceDescription(), beanName, "Invalid destruction signature", ex);
        }

        return exposedObject;
    }
```

一个 Spring Bean 从创建到销毁的完整生命周期非常复杂，但关键步骤如下：

1. **实例化 (Instantiation)**：Spring 容器根据 Bean 的定义，通过反射创建出 Bean 的实例。
2. **属性填充 (Populate Properties)**：Spring 容器为 Bean 的属性注入依赖值（DI）。
3. **Aware 接口回调**：如果 Bean 实现了各种 Aware 接口（如 BeanNameAware, BeanFactoryAware），Spring 会调用这些接口的方法，将相应的资源（如 Bean 的名字、Bean 工厂）注入给 Bean。
4. **BeanPostProcessor****前置处理**：执行所有 BeanPostProcessor 的 postProcessBeforeInitialization 方法。这是一个重要的扩展点。
5. **初始化 (Initialization)**：

- 如果 Bean 实现了 InitializingBean 接口，执行 afterPropertiesSet 方法。
- 如果配置了 init-method，执行指定的初始化方法。

1. **BeanPostProcessor****后置处理**：执行所有 BeanPostProcessor 的 postProcessAfterInitialization 方法。AOP 的代理就是在这里创建的。
2. **Bean 可用**：至此，Bean 创建完成，可以被应用程序使用。
3. **销毁 (Destruction)**：当容器关闭时：

- 如果 Bean 实现了 DisposableBean 接口，执行 destroy 方法。
- 如果配置了 destroy-method，执行指定的销毁方法。

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1763993227388-105f91b6-f387-4b5a-b78d-bbb9c045742d.png)

### Bean是否单例？

**默认是单例（Singleton）的。** 但可以配置为其他作用域。

### Bean的单例和非单例，生命周期是否一样

**不一样。**

- **单例（Singleton）**：Spring 容器**完整地管理**其生命周期，从创建到初始化，再到最终的销毁。
- **原型（Prototype）**：Spring 容器只负责**创建和初始化**这个 Bean，然后将其交给调用者。之后，Spring **不再管理这个 Bean 的生命周期**，也不会调用其销毁方法。对象的销毁由调用者自己负责。

### Spring bean的作用域有哪些？

- **singleton**：**默认作用域**。在整个 Spring 容器中，只有一个 Bean 实例。
- **prototype**：每次请求（通过 getBean 或注入）都会创建一个新的 Bean 实例。
- **request**：每次 HTTP 请求都会创建一个新的 Bean 实例。仅适用于 Web 应用。
- **session**：每个 HTTP Session 都会创建一个新的 Bean 实例。仅适用于 Web 应用。
- **application**：每个 ServletContext 生命周期内创建一个 Bean 实例。仅适用于 Web 应用。

### Spring容器里存的是什么？

主要存两样东西：

1. **Bean 的定义（BeanDefinition）**：这是一个内部数据结构，包含了关于 Bean 的所有元信息，比如它的类名、作用域、是否懒加载、依赖关系、初始化方法等。容器通过它来指导如何创建 Bean。
2. **单例 Bean 的实例（Singleton Beans）**：对于单例作用域的 Bean，容器在创建后会将其缓存起来（即一级缓存 singletonObjects），以便后续直接返回，而不是重复创建。

### 在Spring中，在bean加载/销毁前后，如果想实现某些逻辑，可以怎么做

1. **使用****InitializingBean****和****DisposableBean****接口**：

- 实现 InitializingBean 接口，重写 afterPropertiesSet() 方法，在属性填充后执行。
- 实现 DisposableBean 接口，重写 destroy() 方法，在 Bean 销毁前执行。

1. **使用****@PostConstruct****和****@PreDestroy****注解**：

- 这是 JSR-250 规范的注解，是更推荐的方式，因为它不与 Spring 代码耦合。
- 在一个方法上标注 @PostConstruct，该方法会在依赖注入完成后执行。
- 在一个方法上标注 @PreDestroy，该方法会在 Bean 销毁前执行。

1. **使用****init-method****和****destroy-method****配置**：

- 在 @Bean 注解或 XML 配置中指定初始化和销毁方法的名字。

1. **实现****BeanPostProcessor****接口**（最强大的方式）：

- 这是一个全局的扩展点，它会对容器中**所有**的 Bean 生效。
- postProcessBeforeInitialization()：在任何 Bean 的初始化回调（如 @PostConstruct）之前执行。
- postProcessAfterInitialization()：在任何 Bean 的初始化回调之后执行。Spring AOP 就是通过这个方法来实现代理的包装。

### Spring给我们提供了很多扩展点，这些有了解吗？

- **BeanFactoryPostProcessor**：

- 在 Spring 容器**加载了 Bean 的定义信息之后，但尚未实例化任何 Bean 之前**执行。
- 它允许你**修改 Bean 的定义信息**（BeanDefinition）。例如，你可以用它来修改某个 Bean 的属性值，甚至改变它的作用域。MyBatis 与 Spring 的整合插件就用到了它。

- **BeanPostProcessor**：

- 在 Bean **实例化和依赖注入完成之后，初始化方法（\****init-method）前后**执行。
- 它操作的是 **Bean 的实例**，而不是定义。
- Spring 的 AOP、@Autowired 注解的处理、@PostConstruct 注解的处理等核心功能，都是通过 BeanPostProcessor 的不同实现来完成的。

- **Aware****系列接口**：

- 让 Bean 能够感知到并获取 Spring 容器的资源，如 ApplicationContextAware, BeanNameAware 等。

- **ApplicationListener**：

- 用于监听 Spring 容器发布的事件（如 ContextRefreshedEvent 表示容器刷新完成），实现事件驱动编程。