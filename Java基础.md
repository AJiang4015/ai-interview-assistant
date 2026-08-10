# 概念

### Java 特点

### Java 优势与劣势

### Java 为什么是跨平台的

### JVM、JDK、JRE 三者关系



### JVM 是什么？

我们平时写的代码为人类可以理解的 java 语言，编译器将其转为与平台无关的字节码，jvm 可以看懂字节码并按照上面的指令运行，并且将其翻译成其他平台可以读懂的语言。



### 值传递与引用传递？

java只存在值传递，“引用”传递传的是地址值，而不是引用变量本身。

# 数据类型

### 八种基本的数据类型

byte1，short2，int4，long8，float4，double8，char1，boolean1

### long和int可以互转吗？

可以，long转int，可能存在精度缺失

### 数据类型转换方式你知道哪些？

显式隐式转换

### 类型互转会出现什么问题吗？

数据溢出/截断，精度丢失

### 为什么用bigDecimal 不用double ?

double 和 float 是为科学计算和工程计算设计的，它们是二进制浮点数，无法精确表示很多十进制小数。

在涉及金额统一使用bigdecimal

### 装箱和拆箱是什么？

数据类型和其包装对象的转换

### Java为什么要有Integer？

1. **集合类的使用**：Java的集合类（如 ArrayList, HashMap）只能存储对象，不能存储基本数据类型。要将 int 存入 ArrayList，必须先将其“装箱”成 Integer 对象。ArrayList<int> 是非法的，必须写成 ArrayList<Integer>。
2. **泛型**：泛型参数 <T> 必须是对象类型，不能是基本数据类型。
3. **提供null值**：Integer 是一个对象，可以被赋值为 null，这在很多业务场景中可以用来表示“未赋值”、“不存在”或“未知”的状态。而 int 的默认值是 0，无法表达这种null的语义。
4. **包含有用的方法和常量**：Integer 类提供了很多静态方法和常量，如 Integer.parseInt()、Integer.MAX_VALUE 等。

### 那为什么还要保留int类型？

内存小，性能高。纯粹计算使用

### 说一下 integer的缓存

为了提高性能和节省内存，Java对 Integer 对象实现了一个**缓存机制**。

- **IntegerCache**：Integer 类内部有一个静态内部类 IntegerCache，它在类加载时会提前创建并缓存一个 Integer 对象数组。
- **缓存范围**：默认情况下，缓存的范围是 **-128 到 127**。
- **工作原理**：

- 当你通过 Integer.valueOf(int i) 方法（或自动装箱）创建一个 Integer 对象时，它会首先检查这个 int 值是否在缓存范围内（-128 to 127）。
- **如果在范围内**，它会直接返回缓存中已经存在的那个 Integer 对象的引用。
- **如果不在范围内**，它才会 new Integer(i) 创建一个新的对象。

```java
private static class IntegerCache {
    static final int low = -128;
    static final int high;
    static final Integer cache[];

    static {
        // high value may be configured by property
        int h = 127;
        String integerCacheHighPropValue =
        sun.misc.VM.getSavedProperty("java.lang.Integer.IntegerCache.high");
        if (integerCacheHighPropValue != null) {
            try {
                int i = parseInt(integerCacheHighPropValue);
                i = Math.max(i, 127);
                // Maximum array size is Integer.MAX_VALUE
                h = Math.min(i, Integer.MAX_VALUE - (-low) -1);
            } catch( NumberFormatException nfe) {
                // If the property cannot be parsed into an int, ignore it.
            }
        }
        high = h;

        cache = new Integer[(high - low) + 1];
        int j = low;
        for(int k = 0; k < cache.length; k++)
        cache[k] = new Integer(j++);

        // range [-128, 127] must be interned (JLS7 5.1.7)
        assert IntegerCache.high >= 127;
    }

    private IntegerCache() {}
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763992891144-ce536447-201f-499e-b6f3-1909bb91074d.gif)

# 面向对象

### 怎么理解面向对象？

**面向对象编程（OOP）** 是一种编程思想，它将现实世界中的事物抽象成程序中的**对象（Object）**。

简单来说，就是**把数据（属性）和操作这些数据的方法（行为）封装在一起，形成一个独立的对象**。程序就是由这些对象之间互相协作、通信来完成的。

核心思想是**封装、继承、多态**。

### 封装继承多态

- **封装 (Encapsulation)**：

- **是什么**：将对象的**属性（数据）隐藏**在对象内部，不允许外部直接访问。同时，提供**公共的方法（接口）**来让外部间接地操作这些属性。
- **怎么做**：使用 private 关键字修饰属性，使用 public 的 getter 和 setter 方法来访问。
- **好处**：保证了数据的安全性和完整性，使用者无需关心内部实现细节。

- **继承 (Inheritance)**：

- **是什么**：子类可以获取父类的属性和方法。这是实现**代码复用**的重要方式。
- **怎么做**：使用 extends 关键字。
- **好处**：提高了代码的复用性，建立了类之间的层次关系（“is-a”关系，例如：Dog is a Animal）。

- **多态 (Polymorphism)**：

- **是什么**：“多种形态”。指同一个接口（或方法调用），由于传入的对象实例不同，会表现出不同的行为。
- **前提**：继承、方法重写、父类引用指向子类对象。
- **例子**：Animal animal = new Dog(); animal.makeSound(); 这里调用的是 Dog 类的 makeSound 方法。如果 animal = new Cat();，则会调用 Cat 类的 makeSound 方法。

### 多态体现在哪几个方面？

方法重写

方法重载

接口实现

### 多态解决了什么问题？

多态主要解决了**代码的扩展性和可维护性**问题。

- **解耦合**：它将“做什么”（接口/父类）和“怎么做”（具体实现/子类）分离开来。调用者只需要关心父类或接口，而不需要关心具体的子类实现。
- **提高扩展性**：如果要增加一个新的功能（例如增加一个 Tiger 类），只需要让它继承 Animal 并实现自己的 makeSound 方法即可。对于已有的调用代码（例如一个遍历动物并让它们发出声音的方法），完全不需要做任何修改。这符合**开闭原则**（对扩展开放，对修改关闭）。
- **代码更通用**：可以编写更通用的代码。例如，一个方法 feed(Animal animal) 可以接受任何 Animal 的子类对象作为参数，而不需要为 Dog, Cat, Tiger 分别写一个 feed 方法。

### 面向对象的设计原则你知道有哪些吗

单一职责

开闭原则

接口隔离

依赖倒置

里氏替换原则

### 重载与重写有什么区别？

重载，一个类里面同名方法参数不同

重写，子类重新实现父类方法

### 抽象类和普通类区别？

无法实例化，只能被继承。包含抽象方法。

### Java抽象类和接口的区别是什么？

只能继承一个抽象类，可以实现多个接口。

抽象类为定义，接口为能力

### 抽象类能加final修饰吗？

不可以。抽象类需要被继承实现，final关键字修饰后无法继承。

### 接口里面可以定义哪些方法？

7之前，抽象方法

8，抽象，defualt，static

### 抽象类可以被实例化吗？

不可以

### 接口可以包含构造函数吗？

不可以。

### 非静态内部类可以直接访问外部方法，编译器是怎么做到的？

非静态内部类之所以能访问外部类的成员，是因为 Java 编译器在**编译阶段**做了以下处理：

1. 为内部类增加一个指向外部类实例的隐藏字段 `this$0`
2. 修改构造方法，使其必须接受一个外部类实例
3. 将外部成员访问重写为 `this$0.xxx`
4. 若访问 private 成员，自动生成 synthetic 的桥接方法

因此，内部类访问外部类成员完全是编译器层面的语法糖，而不是 JVM 原生支持。

# 关键字

### final

- 类：无法被继承，Stirng
- 方法：无法被重写，Object的getClass
- 属性：常量

### static

- 方法，属于类
- 属性，属于类
- 代码块，用于初始化
- 内部类，独立外部对象

# 深拷贝与浅拷贝

### 区别

- 浅拷贝对于引用数据类型，复制引用地址。
- 深拷贝递归复制引用数据类型的对象。

### 实现深拷贝的3种方法

1. 重写clone方法，除了super.clone，还有**手动地**对所有引用类型的成员也调用它们的 clone() 方法。
2. 序列化。序列化再反序列化成一个新对象
3. 手动递归复制

# 泛型

### 定义

 泛型允许在编译期对集合或对象的类型进行约束，使代码在运行时不会发生类型转换错误。  

# 对象

### 创建对象的方法

1. new
2. 反射，使用Constructor类的newInstance()方法
3. 反序列化
4. 工厂模式
5. clone

### new出的对象什么时候被回收

1. **核心概念：可达性分析 (Reachability Analysis)**

- Java的垃圾回收机制通过“可达性分析”算法来判断对象是否存活。
- 这个算法会从一组称为 **“GC Roots”** 的对象开始，向下遍历引用链。
- 所有能从 GC Roots 最终访问到的对象，都被认为是**存活的（可达的）**。
- 所有不能从 GC Roots 访问到的对象，都被认为是**垃圾（不可达的）**。

1. **什么是GC Roots？**

- **虚拟机栈**（栈帧中的本地变量表）中引用的对象。
- **方法区**中类静态属性引用的对象。
- **方法区**中常量引用的对象。
- **本地方法栈**中JNI（即Native方法）引用的对象。
- 被同步锁（synchronized）持有的对象。

1. **回收时机**

- 一个对象变为不可达后，它仅仅是**有资格被回收**。
- **真正的回收动作**是由GC线程在未来的某个不确定的时间点执行的。这个时间点由JVM根据堆内存的使用情况、系统负载等因素自行决定。
- 所以，你无法精确预测一个对象何时被回收，也无法（也不应该）通过代码强制GC立即回收某个对象（System.gc() 只是一个“建议”，JVM可以忽略）。

当一个 new 出来的对象，没有任何引用链能从任何一个 GC Root 追溯到它时，它就成了垃圾，等待GC在未来的某个时间点进行回收。

### 如何获取私有对象

通过 **Java反射 (Reflection)** 机制，可以**强行**访问和修改它们。

**步骤如下：**

1. 获取目标类的 Class 对象。
2. 通过 Class 对象获取指定的 Field (字段) 或 Method (方法) 对象。**必须使用****getDeclaredField()****或****getDeclaredMethod()**，因为 getField() 和 getMethod() 只能获取 public 成员。
3. **关键一步**：调用 field.setAccessible(true) 或 method.setAccessible(true)。这会取消Java语言的访问权限检查。
4. 通过 field.get(objectInstance) 获取字段值，或通过 method.invoke(objectInstance, args) 调用方法。

# 反射

### 什么是反射？

程序可以在**运行时**动态地：

- 获取任意一个类的完整结构信息（包括它的字段、方法、构造器、父类、接口、注解等）。
- 在运行时创建一个类的实例。
- 在运行时获取和设置任意一个对象的字段值（即使是private的）。
- 在运行时调用任意一个对象的方法（即使是private的）。

### 反射在你平时写代码或者框架中的应用场景有哪些？

1. **Spring 框架的 IoC/DI**：

- **IoC (Inversion of Control)**：Spring容器通过读取XML或扫描注解（如 @Component, @Service），利用反射 (Class.forName(), clazz.newInstance()) 来创建和管理Bean对象，而不需要我们手动new。
- **DI (Dependency Injection)**：Spring在创建Bean后，会检查其字段或setter方法上的 @Autowired 注解，然后利用反射（field.setAccessible(true), field.set(bean, dependency)) 将依赖的对象注入进去。

1. **ORM框架 (MyBatis, Hibernate)**：

- 当从数据库查询出一条记录时，MyBatis需要将 ResultSet 里的数据填充到一个Java对象（POJO）中。它就是通过反射获取POJO的所有字段，然后根据字段名（或注解映射）与数据库列名的对应关系，使用 field.set() 方法将值赋给对象的私有字段。

1. **动态代理 (Dynamic Proxy)**：

- java.lang.reflect.Proxy 类可以动态地创建一个实现了指定接口的代理对象。所有对代理对象方法的调用都会被转发到一个 InvocationHandler 接口的实现上。这在Spring AOP（面向切面编程）中被广泛用于实现日志、事务、权限控制等功能，而无需修改业务代码。

1. **注解处理器**：

- 框架（如JUnit）通过反射查找被特定注解（如 @Test）标记的方法，然后动态地调用这些方法来执行单元测试。

1. **序列化/反序列化库 (Jackson, Gson)**：

- 当把一个Java对象转换成JSON字符串时，这些库需要通过反射读取对象的所有字段（包括私有）的值。反之，从JSON字符串创建Java对象时，也需要通过反射调用构造函数并设置字段值。

# 代理

### 动态代理

动态代理的逻辑与静态代理一致，但动态代理不需要手写代理类，而是由框架在运行时（JVM）动态生成代理类，并能根据运行时规则动态织入多个横切逻辑，从而实现 AOP、事务、缓存、权限等框架级能力。 

| 项目                | JDK 动态代理           | CGLIB 代理                                   |
| ------------------- | ---------------------- | -------------------------------------------- |
| **是否 JDK 自带**   | ✔ 官方                 | ❌（Spring 内置 CGLIB/ASM，但是不是 JDK API） |
| **是否需要接口**    | ✔ 必须                 | ✘ 不需要                                     |
| **原理**            | 生成接口实现类         | 生成目标类的子类（继承）                     |
| **无法代理的情况**  | 没有接口的类           | final 类、final 方法                         |
| **性能**            | 调用慢一点（反射调用） | 快（直接方法调用）                           |
| **Spring 默认策略** | 有接口 → JDK Proxy     | 无接口 → CGLIB                               |





# 注解

### 能讲一讲Java注解的原理吗？

注解本质上是 `继承了 Annotation 接口的接口`，即：

```java
public @interface MyAnno {}
```

编译后变成：

```java
public interface MyAnno extends java.lang.annotation.Annotation {}
```

 Java 注解本质是继承 Annotation 的接口，编译后注解存储在 class 的属性表中。
RUNTIME 注解在运行时可通过反射读取，Spring 使用 ASM 做字节码扫描和元数据读取。  

### 对注解解析的底层实现了解吗？

底层实现主要依赖于**反射**。

当一个注解的 RetentionPolicy 被设置为 RUNTIME 时，它的信息会被加载到JVM中。在运行时，我们可以通过反射API来获取这些信息。

**底层流程：**

1. **加载类**：JVM加载包含注解的 .class 文件。
2. **获取Class对象**：我们通过代码获取到被注解的类、方法或字段对应的 Class, Method, Field 对象。
3. **调用getAnnotation()**：这些反射对象都提供了一系列方法来读取注解，最核心的是 getAnnotation(Class<T> annotationClass)。
4. **返回代理对象**：当我们调用 getAnnotation() 时，JVM并不会返回一个我们自己写的注解接口的实例。相反，它会**动态地创建一个代理对象**（使用 java.lang.reflect.Proxy），这个代理对象实现了我们的注解接口。
5. **访问属性**：当我们调用注解的属性方法（如 myAnnotation.value()）时，实际上是调用了代理对象的相应方法。代理对象内部会持有一个Map，存储着我们在代码中为注解属性赋的值。调用方法时，它就从这个Map里查找并返回值。

这就是为什么我们可以像调用普通接口方法一样，从注解实例中获取到我们设置的属性值。

### Java注解的作用域呢？

注解的作用域由元注解 @Retention 来定义，它指定了注解的生命周期。有三种策略（RetentionPolicy）：

1. RetentionPolicy.SOURCE:

- **作用域**：仅存在于**源代码**（.java文件）中。
- **行为**：编译器在编译时会直接丢弃这些注解。
- **用途**：主要用于给编译器提供信息，或由一些预处理工具（如Lombok）使用。例如 @Override（帮助编译器检查是否正确重写），@SuppressWarnings，以及Lombok的 @Data、@Getter等。

1. RetentionPolicy.CLASS:

- **作用域**：存在于**字节码**（.class文件）中，但在运行时会被JVM丢弃。
- **行为**：默认的保留策略。
- **用途**：可以在编译期进行一些字节码增强操作，但运行时无法获取。用得相对较少。

1. RetentionPolicy.RUNTIME:

- **作用域**：存在于**字节码**中，并且在**运行时**会被加载到JVM中。
- **行为**：可以通过反射机制在程序运行时读取和使用。
- **用途**：这是最常用的一种，绝大多数框架（如Spring、MyBatis、JUnit）都使用这种策略，以便在运行时根据注解来执行相应逻辑。

# 异常

### 介绍一下Java异常

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1763992891408-ea40f004-d644-44ef-969c-c381a9f63d99.png)

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763992891142-03502769-6b56-4907-9cc0-e047e2729bca.gif)编辑

异常（Exception）是程序在**运行期间**发生的不正常事件，它中断了程序的正常指令流。

runtime异常为需要手动需求的代码bug，check异常为需要捕获处理的异常。

### Java异常处理有哪些？

- try-catch-finally，捕获处理异常
- throws，声明抛出异常
- throw，手动抛出异常

### tryfreturn "a"} finally{return"b"｝这条语句返回什么？

返回b。

# Object

### == 与 equals 有什么区别？

- == 比较内存地址
- equals 一般被重写为比较内容

### hashcode和equals方法有什么关系？

当你重写一个类的 equals() 方法时，必须同时重写它的 hashCode() 方法，以保证“相等的对象有相等的哈希码”这个约定。

不重写hashCode方法，可能导致Set集合里面出现一样的value

### String, StringBuffer,StringBuilder的区别和联系

区别在于是否为线程安全。

- String 本身和内部 char 数组用了 final 关键字。为线程安全。用于常量
- StringBuffer，通过给公共方法加上 sync 关键字，实现线程安全。多线程频繁修改
- StringBuilder 功能与 StringBuffer 一致，除了线程安全。

# java新特性

### Java 8 你知道有什么新特性？

- Lambda表达式
- Stream流编程
- 接口默认方法和静态方法
- Option<T>类
- 新的日期时间API
- completableFuture异步编程

### Lambda 表达式了解吗？

简洁匿名内部类

### Java中stream的API介绍一下

创建stream，中间操作，终端操作

### Stream流的并行API是什么？

你只需要将 stream() 换成 parallelStream()，就可以让 Stream 的操作**在多个 CPU 核心上并行执行**。

### completableFuture怎么用的？

提供非阻塞，回调式线程模型。

# 序列化

### 怎么把一个对象从一个jvm转移到另一个jvm？

**序列化 → 网络传输 → 反序列化。**

**常见的实现方法有：**

1. **Java内置序列化**：

- **原理**：让对象类实现 java.io.Serializable 标记接口。使用 ObjectOutputStream 将对象写入字节流，使用 ObjectInputStream 从字节流中读出并重建对象。
- **传输媒介**：可以通过网络套接字（Sockets）、远程方法调用（RMI）、消息队列（JMS）等方式传输生成的字节流。
- **优点**：实现简单，是Java原生支持。
- **缺点**：性能较差，字节流体积大，有安全漏洞风险，且与语言强绑定。

1. **使用JSON格式**：

- **原理**：使用Jackson、Gson、Fastjson等库，将对象转换为JSON字符串。JSON字符串本质上也是一种字节流（如UTF-8编码）。
- **传输媒介**：通过HTTP/REST API、消息队列等方式传输JSON字符串。
- **优点**：可读性好，跨语言，生态丰富。是目前Web服务间通信的主流方式。

1. **使用二进制协议（如Protobuf, Avro, Thrift）**：

- **原理**：定义一个IDL（接口定义语言）文件（如.proto）来描述数据结构，然后使用工具生成对应语言的代码。序列化和反序列化由生成的代码完成。
- **传输媒介**：常用于高性能的RPC（远程过程调用）框架中，如gRPC、Dubbo。
- **优点**：性能极高，序列化后体积小，协议向前向后兼容性好。

1. **通过数据库**：

- **原理**：JVM A 将对象的状态持久化到共享的数据库（如MySQL, Redis）中。JVM B 从数据库中读取这些状态，然后在自己的内存中重建对象。
- **优点**：解耦了两个JVM，提供了持久化能力。

**总结**：不论哪种方法，本质都是 **序列化 -> 传输 -> 反序列化** 的过程。选择哪种方法取决于具体的应用场景（如性能要求、是否需要跨语言、是否需要可读性等）。

### 序列化和反序列化让你自己实现你会怎么做？

一个对象序列化需要：

1. 将对象字段遍历
2. 把字段名、字段类型、字段值写到二进制流
3. 反序列化时根据元信息恢复对象

### 将对象转为二进制字节流具体怎么实现？

让类实现Serializable 接口。

在Java中通过序列化对象流来完成序列化和反序列化：

ObjectOutputStream:通过writeObject(方法做序列化操作。

ObjectInputStream：通过readObject(方法做反序列化操作。

# 设计模式

### volatile和sychronized如何实现单例模式

```java
class A {
    private static volatile A a;

    private A(){}

    public static A get(){
        if(a == null){
            synchronize(this){
                if(a == null){
                    a = new A();
                }
            }
        }
        return a;
    }
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763992891135-26a5fdd7-f8fc-4531-9994-5a704b0c4194.gif)

### 代理模式和适配器模式有什么区别？

代理是增强，适配器是兼容。

目的不同：代理模式主要关注控制对对象的访问，而适配器模式则用于接口转换，使不兼容的类能够

一起工作。

结构不同：代理模式一般包含抽象主题、真实主题和代理三个角色，适配器模式包含目标接口、适配

器和被适配者三个角色。

应用场景不同：代理模式常用于添加额外功能或控制对对象的访问，适配器模式常用于让不兼容的接

口协同工作。

# IO

### Java怎么实现网络IO高并发编程？

使用 **非阻塞I/O (NIO)** 或 **异步I/O (AIO)**。

核心思想是**用少量线程处理大量连接**，从而避免因大量线程导致的内存开销和线程上下文切换的性能损耗。

1. **Java NIO (Non-blocking I/O)**:

- 使用 **I/O多路复用 (I/O Multiplexing)** 技术。
- **核心组件**: Selector（多路复用器）、Channel（通道）、Buffer（缓冲区）。
- **工作模式**:

- 将所有连接（Channel）注册到一个 Selector 上。
- 用一个（或少量）线程调用 selector.select() 方法进行阻塞，等待任意一个 Channel 变为“就绪”状态（如可读、可写）。
- 一旦有 Channel 就绪，select() 方法返回，线程被唤醒。
- 线程遍历这些就绪的 Channel，进行相应的读写操作。这些操作通常是**非阻塞**的，能读多少读多少，能写多少写多少，然后立即返回。
- 处理完所有就绪的 Channel 后，线程再次调用 select() 进入等待状态。

- **优点**: 一个线程可以管理成千上万个连接，极大地提高了服务器的并发能力。

1. **Java AIO (Asynchronous I/O, 也叫 NIO.2)**:

- 基于**事件驱动**的异步模型（Proactor模式）。
- **工作模式**:

- 应用程序发起一个I/O操作（如读或写），并**提供一个回调函数（\****CompletionHandler）**。
- 应用程序的线程**不等待**I/O操作完成，立即返回去做其他事情。
- 操作系统在后台完成I/O操作。
- 当I/O操作完成后，操作系统**通知**应用程序，并调用之前提供的回调函数来处理结果。

- **优点**: 编程模型更简单直观，实现了真正的异步，线程可以被更充分地利用。

**结论**：在现代Java高并发网络编程中，**NIO是主流和基石**。AIO虽然理论上更先进，但在Linux上底层实现仍是epoll（与NIO相同），优势不明显，且生态和成熟度不如NIO，因此实际应用中，基于NIO的框架（如Netty）更受欢迎。

### BIO、NIO、AIO区别是什么？

同步阻塞

同步非阻塞

异步非阻塞

### NIO是怎么实现的？

1. **三大核心组件**:

- **Channel (通道)**: 类似于BIO中的Stream，是数据传输的管道，但它是双向的，并且可以配置为非阻塞模式。常见的有SocketChannel, ServerSocketChannel, FileChannel。
- **Buffer (缓冲区)**: 一块内存区域。NIO中所有的数据读写都必须通过Buffer。数据先从Channel读到Buffer，再从Buffer写入Channel。Buffer有position, limit, capacity等状态来管理数据。
- **Selector (选择器/多路复用器)**: 这是NIO实现高并发的**核心**。它允许一个线程监视多个Channel的I/O事件（如连接、可读、可写）。

1. **工作流程**:

1. 创建一个 Selector。
2. 创建一个或多个 Channel（如ServerSocketChannel用于监听连接）。
3. 将 Channel 设置为**非阻塞模式** (channel.configureBlocking(false))。
4. 将 Channel **注册**到 Selector 上，并指定你感兴趣的**事件类型**（SelectionKey.OP_ACCEPT, OP_READ等）。
5. 在一个循环中，调用 selector.select()。这个方法会**阻塞**，直到至少有一个注册的Channel发生了你感兴趣的事件。
6. select() 返回后，通过 selector.selectedKeys() 获取所有已就绪的 SelectionKey 集合。
7. 遍历 selectedKeys 集合，根据每个 SelectionKey 的事件类型，进行相应的I/O操作（例如，如果是 OP_ACCEPT，就接受新连接；如果是 OP_READ，就从Channel读取数据到Buffer）。
8. 处理完一个 SelectionKey 后，**必须手动将其从集合中移除** (iterator.remove())，否则下次select()会立即返回，处理同一个事件，导致死循环。
9. 继续下一次循环，再次调用 select() 等待新的事件。

**底层系统调用**:

- 在 **Linux** 上，Selector 底层主要使用 epoll。
- 在 **Windows** 上，使用 select 或 IOCP。 epoll 是性能最高的，它避免了传统 select 和 poll 的轮询所有文件描述符的开销，只返回真正就绪的描述符。

### 你知道有哪个框架用到NIO了吗？

1. **Netty**: 这是最著名、最广泛使用的基于NIO的客户端/服务器端网络应用框架。它极大地简化了NIO的复杂性，并提供了稳定、高效的实现。**是事实上的标准**。
2. **Mina**: 另一个流行的NIO框架，与Netty类似，但目前社区活跃度和使用广泛度不如Netty。
3. **Grizzly**: Sun/Oracle开发的一个NIO框架，是GlassFish应用服务器的底层网络层。
4. **Tomcat / Jetty / Undertow**: 现代的Web服务器都提供了基于NIO的连接器（Connector），以支持高并发的HTTP请求处理。
5. **RPC框架**: 如 **Dubbo**、**gRPC** 等，它们的底层网络通信模块都依赖于NIO（通常是基于Netty实现的）。
6. **消息队列**: 如 **RocketMQ**，其NameServer和Broker之间的通信也是基于Netty（NIO）的。
7. **数据库驱动**: 一些高性能的数据库驱动程序，如**Lettuce**（Redis的Java客户端），也使用NIO来处理与数据库的异步通信。

# 

# 