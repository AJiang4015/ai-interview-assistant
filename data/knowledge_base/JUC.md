# 线程

## 如何创建线程？

一般来说，创建线程有很多种方式，例如继承 Thread 类、实现 Runnable 接口、实现 Callable 接口、使

用线程池、使用 CompletableFuture 类等等。

不过，这些方式其实并没有真正创建出线程。准确点来说，这些都属于是在 Java 代码中使用多线程的方

法。

严格来说，Java 就只有一种方式可以创建线程，那就是通过 `new Thread（）.start（）`创建。不管是哪种方式，最终还是依赖于 new Thread（）.start（）。

## 线程的生命状态和周期

Java线程在运行的生命周期中的指定时刻只可能处于下面6种不同状态的其中一个状态：

- NEW：初始状态，线程被创建出来但没有被调用 start（）。
- RUNNABLE：运行状态，线程被调用了 start（）等待运行的状态。
- BLOCKED：阻塞状态，需要等待锁释放。
- WAITING：等待状态，表示该线程需要等待其他线程做出一些特定动作（通知或中断）。
- TIME_WAITING： 超时等待状态，可以在指定的时间后自行返回而不是像 WAITING 那样一直等待。
- TBRMINATED：终止状态，表示该线程已经运行完毕。

线程在生命周期中并不是固定处于某一个状态而是随着代码的执行在不同状态之间切换

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1763993321769-e88e2f89-442b-4e2a-a093-8412c719bce3.png)

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321673-85edce6c-75a2-4e03-8f76-c8660986687f.gif)编辑

## Thread#sleep()对比 Object#wait()方法对比

**共同点：**两者都可以暂停线程的执行。

**区别：**

- sleep() 方法没有释放锁，而 wait() 方法释放了锁。
- wait() 通常被用于线程间交互/通信，sleep() 通常被用于暂停执行。
- wait() 方法被调用后，线程不会自动苏醒，需要别的线程调用同一个对象上的 notify() 或者 notifyALL() 方法。sleep() 方法执行完成后，线程会自动苏醒，或者也可以使用 wait(long timeout）超时后线程会自动苏醒。
- sleep() 是 Thread 类的静态本地方法，wait() 则是 object 类的本地方法。

## 为什么 wait() 要定义在 Object 类中

wait（）是让获得对象锁的线程实现等待，会自动释放当前线程占有的对象锁。每个对象（Object）都

拥有对象锁，既然要释放当前线程占有的对象锁并让其进入 WAITING状态，自然是要操作对应的对象

（Object）而非当前的线程（Thread）。

类似的问题：为什么 sleep（）方法定义在 Thread 中？

因为 sleep（）是让当前线程暂停执行，不涉及到对象类，也不需要获得对象锁。

# 线程池

## 工作原理

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149778012-1ce2e77c-7c27-4ec7-aaa6-4806324620bf.png)

## 线程池参数

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149779707-b0e0c68e-fb32-4316-beef-cd9d77f7d174.png)

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764149778927-01542f9c-f02b-44d8-be6e-cc165dde7898.gif)编辑

- corePoolSize：核心线程数，即使空闲也不会被销毁
- maximumPoolSize：最大线程数（包括核心非核心），当核心线程数达到最大和队列满的情况下，创建新线程，线程达到最大线程数，执行拒绝策略
- keepAliveTime：非核心线程空闲时间最长存活时间
- unit：单位
- workQueue：工作队列
- threadfactory：线程工厂，一般用来起名字
- handler：拒绝策略

## 拒绝策略

- **AbortPolicy**  抛出RejectedExecutionException 来拒绝新任务的处理。

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149778912-fa946fcb-069a-4f45-ace5-57457da77f3f.png)

- **CallerRunsPolicy**  调用执行者自己的线程运行任务，如果执行程序已关闭，则会丢弃该任务。

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149781418-e6cfe445-df4b-4155-9eb4-cbef170598fc.png)

- **DiscardOldestPolicy**  丢弃最早的未处理的任务请求。

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149782383-df5441cd-66bc-476c-8386-d3ba5d3d883c.png)

- **DiscardPolicy** 直接丢弃

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149783431-9d9dd0d5-1ab3-413d-a37f-4833d530766f.png)

## corePoolSize是否可以为0？

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149783842-36bfff53-c096-4ff7-be70-fc1be596b086.png)

**ctl****是一个****AtomicInteger****类型的变量，它代表了线程池的“控制状态”（Control State）**。一个 int 32位，分成两部分记录线程池信息

- **高3位 (bit 29-31)**：用于存储 runState。
- **低29位 (bit 0-28)**：用于存储 workerCount。

```plain
| 31 30 29 | 28  ...   ...   ...   0 |
+----------+-------------------------+
| runState |       workerCount       |
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764149783905-55fd1d48-4101-4c8f-8bdc-d141a477681b.gif)

1. int c = ctl.get();

- **作用**：原子性地读取 ctl 的当前值，这个值 c 同时包含了**此刻的运行状态**和**工作线程数**。

1. if (workerCountOf(c) < corePoolSize)

- **作用**：workerCountOf(c) 是一个辅助方法，它通过位运算 (c & CAPACITY) 从 c 中**仅提取出低29位**，也就是 workerCount。
- 这行代码判断：当前工作线程数是否小于核心线程数。

1. if (isRunning(c) && workQueue.offer(command))

- **作用**：isRunning(c) 是另一个辅助方法，它通过位运算 (c < SHUTDOWN) 判断 c 中包含的 runState 是否为 RUNNING。
- 这行代码判断：如果线程池正在运行，就尝试将任务放入工作队列 workQueue。

不能复用 c，需要重新获取recheck的原因是，不同时间点，线程状态可能发生了变化，需要获取最新值

## 线程池类型

- FixedThreadPool

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149783742-e608ccc1-6326-4d5b-beb2-15fd04d4492e.png)

- CachedThreadPool

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149784282-dd170a4d-3e78-4654-bdae-2d42ea83eebd.png)

- SingleThreadExecutor

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149785007-5170a4e9-4423-4b2c-afcc-d5e129e5dcea.png)

- ScheduledThreadPool

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149784922-8d24b7bd-59b7-44d6-a1f7-7b8c87bbe2d0.png)

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149786025-932f3652-63f7-438f-9037-52a17f8d193b.png)

除了ScheduledThreadPool，其他都只是普通ThreadPool提前封装好参数的返回

## 提交到线程池的任务可以被撤回吗？

submit() 方法返回一个 Future 类参数，cancel() 方法通过参数指定是否可以被中断

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764149787368-4b122df6-1881-499a-85d4-b1dc8a11ef78.png)

## 如何创建线程池

- 通过 `ThreadPoolExecutor` 构造函数直接创建（推荐）
- 通过 `Executors` 工具类创建（不推荐）



## 线程池中线程异常后，销毁还是复用？

使用 execute（）时，未捕获异常导致线程终止，线程池创建新线程替代；使用 submit（）时，异常被封装在 Future 中，线程继续复用。

这种设计允许 submit（）提供更灵活的错误处理机制，因为它允许调用者决定如何处理异常，而execute（）则适用于那些不需要关注执行结果的场景。

## 如何动态修改线程池的参数？

[Java线程池实现原理及其在美团业务中的实践](https://tech.meituan.com/2020/04/02/java-pooling-pratice-in-meituan.html)这篇文章中介绍到对线程池参数实现可自定义配置的思路和方法。

美团技术团队的思路是主要对线程池的核心参数实现自定义可配置。这三个核心参数是：

- corePoolSize：核心线程数定义了最小可以同时运行的线程数量。
- maximumPoolSize：当队列中存放的任务达到队列容量的时候，当前可以同时运行的线程数量变为最大线程数。
- workQueue：当新任务来的时候会先判断当前运行的线程数量是否达到核心线程数，如果达到的话，新任务就会被存放在队列中。

# 多线程

### Java 的内存模型（JMM）介绍一下

Java内存模型（Java Memory Model, JMM）是一个**抽象的概念规范**，它定义了Java程序中各种变量（线程共享变量）的访问规则，以及在多线程环境下，如何以及何时可以看到由其他线程修改过的共享变量的值。

JMM解决了并发编程中的三个核心问题：

1. **可见性（Visibility）**：当一个线程修改了共享变量的值，其他线程能够立即得知这个修改。
2. **原子性（Atomicity）**：一个或多个操作，要么全部执行且执行的过程不会被任何因素打断，要么就都不执行。 
3.  **有序性（Ordering）**：程序执行的顺序按照代码的先后顺序执行。编译器和处理器为了优化性能，可能会对指令进行重排序。

**核心概念：**

- **主内存（Main Memory）**：所有线程共享的内存区域，存储了所有的实例字段、静态字段和构成数组对象的元素。
- **工作内存（Working Memory）**：每个线程私有的内存区域，存储了该线程使用的变量的主内存副本拷贝。线程对变量的所有操作（读取、赋值等）都必须在工作内存中进行，不能直接读写主内存。

JMM规定了工作内存和主内存之间的交互协议，通过 volatile, synchronized, final 等关键字，为开发者提供了保证可见性、原子性和有序性的工具。

### java多线程是什么？需要注意什么？

在一个 Java 程序中同时运行多个线程，这些线程共享程序的内存空间（如全局变量、方法区等），有各自的栈和程序计数器，能同时执行不同的任务。

- 线程安全
- 死锁
- 饥饿
- 资源消耗
- 上下文切换开销

### java里面的线程和操作系统的线程一样吗？

这是一个非常好的问题，它触及了Java并发模型的根本。

简单直接的回答是：**在目前主流的Java版本中（JDK 1.2之后），Java的线程与操作系统的线程是基本一一对应的关系。** 但理解这背后的细节和演变过程非常重要。

我们来详细分解一下：

### 1. 核心关系：映射模型

Java线程（java.lang.Thread对象）本质上是JVM对操作系统**本地线程（Native Thread）\****的一个抽象和封装**。你不能脱离操作系统而谈Java线程的执行。

在现代的HotSpot JVM中，采用的是 **1:1的线程模型**。

- **1 (Java Thread) : 1 (OS Thread)**

- 你每在Java代码中创建一个 Thread 对象并调用 start() 方法，JVM就会在底层调用操作系统的API来创建一个对应的、真实的内核级线程。
- Java线程的**生命周期**与这个内核线程是绑定的。当Java线程的run()方法执行完毕，这个内核线程也会被销毁。
- Java线程的**调度**完全委托给操作系统的调度器（OS Scheduler）。哪个Java线程能获得CPU时间片，在哪个CPU核心上运行，都由操作系统说了算。JVM可以设置线程的优先级（setPriority()），但这只是给操作系统的一个“建议”，操作系统不一定会严格遵守。

### 2. 为什么需要这种映射？

- **利用多核CPU**：只有内核级线程才能被操作系统独立调度到不同的CPU核心上并行执行。如果Java线程不是由OS线程支持，那么在一个多核CPU的机器上，一个Java程序也只能利用一个核心，无法真正实现并行计算。
- **处理阻塞I/O**：当一个线程执行阻塞I/O操作（如读文件、网络请求）时，操作系统可以将该线程挂起，并调度其他线程来使用CPU。如果Java线程和OS线程是1:1的，一个Java线程的阻塞不会影响其他Java线程的运行。

### 3. 历史上的另一种模型：绿色线程 (Green Threads)

在早期的Java版本中（JDK 1.2之前），Java实现了一种被称为**“绿色线程”**的模型。

- **模型**：M:1 模型。即多个（M个）Java线程（绿色线程）被映射到**一个**（1个）操作系统内核线程上。
- **管理与调度**：这些绿色线程的创建、切换和调度完全由JVM在**用户空间（User-space）**自己管理，操作系统对此一无所知。
- **优点**：

- 线程创建和上下文切换非常快，因为它不涉及从用户态到内核态的转换，只是JVM内部数据结构的变换。
- 具有很好的平台无关性，因为不依赖于操作系统的线程实现。

- **致命缺点**：

1. **无法利用多核**：因为所有Java线程都运行在同一个OS线程上，所以程序在任何时候最多只能利用一个CPU核心。
2. **阻塞问题**：如果一个Java线程执行了一个阻塞的系统调用，那么整个OS线程都会被阻塞，导致该OS线程上运行的所有其他Java线程也全部被阻塞，程序失去响应。

由于这些致命的缺点，Java从JDK 1.2开始就放弃了绿色线程，转向了与操作系统线程1:1映射的本地线程模型。

### 4. 未来：虚拟线程 (Virtual Threads) - Project Loom

1:1模型虽然解决了多核利用和阻塞问题，但它也有一个显著的缺点：**OS线程是重量级资源**。

- 创建一个OS线程需要消耗较多的内存（通常是1MB左右的栈空间）。
- 线程的上下文切换涉及内核态，开销较大。
- 操作系统能支持的线程数量是有限的。

这就限制了Java应用程序能够创建的线程数量，使得我们无法轻松地为一个请求创建一个线程（thread-per-request）来处理上百万的并发连接。

为了解决这个问题，Java引入了**Project Loom**，并在**JDK 19**中作为预览功能，**JDK 21**中正式发布了**虚拟线程（Virtual Threads）**。

- **模型**：M:N 模型。即多个（M个）**虚拟线程**被映射到少数（N个）**平台线程（Platform Thread，即传统的OS线程）**上。
- **管理与调度**：虚拟线程是**极其轻量级**的，由JVM自己调度。JVM会将虚拟线程“挂载（mount）”到一个平台线程上执行。当虚拟线程遇到阻塞操作时，JVM会自动将其“卸载（unmount）”，并让这个平台线程去执行另一个就绪的虚拟线程。
- **优点**：

- 可以轻松创建数百万个虚拟线程，内存占用极小。
- 让开发者可以用简单、同步、阻塞式的代码风格，来编写高并发、高吞吐量的程序，而不用去写复杂的回调（Callback Hell）或响应式代码。

### 总结

| **特性**     | **Java 线程 (\******java.lang.Thread****)\****               | **操作系统线程 (Native Thread)**       |
| ------------ | ------------------------------------------------------------ | -------------------------------------- |
| **抽象层级** | JVM层面的高级抽象                                            | 操作系统的底层执行单元                 |
| **管理方**   | JVM（创建、销毁的请求发起者）                                | 操作系统内核（真正的资源分配和管理者） |
| **调度方**   | **（传统线程）** 完全依赖OS调度器 		**（虚拟线程）** 主要由JVM调度 | 由OS调度器负责                         |
| **资源消耗** | **（传统线程）** 重量级，与OS线程相当 		**（虚拟线程）** 极其轻量级 | 重量级，占用内存和内核资源             |
| **当前关系** | **在JDK 21之前的主流模型中**，是1:1的映射关系。一个Java线程对应一个OS线程。 | 是Java线程得以运行的实体。             |

所以，回答你的问题： **不完全一样，但紧密相关。Java线程是一个面向开发者的API和对象，而在现代（非虚拟线程）Java中，它的执行实体就是背后那个1:1绑定的操作系统线程。**

### 使用多线程要注意哪些问题？

- 原子性 synchroinized
- 可见性 volatile
- 有序性 happens-before原则

### 保证数据的一致性有哪些方案呢？

- 事务管理
- 锁
- 版本控制（乐观锁）

### 线程的创建方式有哪些？

- 继承Thread类
- 实现Runnable接口
- 实现Callable接口与FutureTask
- 使用线程池

底层都是使用`new Thread().start()`创建。

### 怎么启动线程？

必须调用 start()，而不是 run()！



### 如何停止一个线程的运行？

**不推荐使用** Thread.stop() 方法，因为它是不安全的。它会立即释放该线程所持有的所有锁，可能导致对象状态不一致。

**推荐的优雅方式是使用中断（Interruption）：**

1. **使用****volatile****标志位**： 定义一个 volatile boolean 标志位，线程在 run() 方法的循环中检查这个标志位。外部线程通过修改这个标志位来通知目标线程停止。

```plain
class MyRunnable implements Runnable {
    private volatile boolean running = true;

    public void stop() {
        this.running = false;
    }

    @Override
    public void run() {
        while (running) {
            // ... do work ...
        }
        System.out.println("线程停止。");
    }
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321669-f9330c71-31d8-42ed-b3e1-10abc0473c50.gif)

1. **使用****Thread.interrupt()****方法（最佳实践）**： interrupt() 方法并不会直接停止线程，而是设置线程的**中断状态位**为 true。线程需要自己检查这个状态位并做出响应。

- 如果线程处于 sleep(), wait(), join() 等阻塞状态，调用 interrupt() 会使它抛出 InterruptedException，并**清除中断状态**。我们可以在 catch 块中处理停止逻辑。
- 如果线程处于运行状态，它需要主动通过 Thread.currentThread().isInterrupted() 来检查中断状态。

```plain
class MyRunnable2 implements Runnable {
    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                System.out.println("线程运行中...");
                Thread.sleep(1000); // 阻塞方法会响应中断
            } catch (InterruptedException e) {
                System.out.println("线程被中断，准备退出。");
                // 重新设置中断状态，因为catch会清除它
                Thread.currentThread().interrupt();
            }
        }
        System.out.println("线程已停止。");
    }
}

public static void main(String[] args) throws InterruptedException {
    Thread t = new Thread(new MyRunnable2());
    t.start();
    Thread.sleep(3000); // 运行3秒
    t.interrupt(); // 发出中断请求
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321672-9adf17b9-728b-4bba-b7cd-e57ba33d3726.gif)

### 调用 interrupt 是如何让线程抛出异常的？

调用interrupt()本身**不会**立即抛出异常。它只是设置了线程的中断标志位。

异常是在以下特定情况下由特定方法抛出的：

- 当一个线程**正在**执行Object.wait(), Thread.sleep(), Thread.join()这些**阻塞方法**时，如果其他线程调用了它的interrupt()方法。
- 那么这个正在阻塞的线程会**立即被唤醒**，并抛出InterruptedException。
- **一个重要的细节**：在抛出InterruptedException后，JVM会自动将该线程的**中断标志位清除（即重置为\****false）**。所以在catch块中，如果你想让调用栈上层的代码也能感知到中断，通常需要再次调用Thread.currentThread().interrupt()来重新设置中断状态。

如果线程没有在执行上述阻塞方法，interrupt()调用仅仅是设置标志位，线程会继续执行，直到它自己通过isInterrupted()来检查这个标志位。

### Java线程的状态有哪些？

Java线程有6种状态，定义在 Thread.State 枚举中：

1. **NEW（新建）**：线程被创建，但尚未调用 start() 方法。
2. **RUNNABLE（可运行）**：线程调用 start() 方法后进入此状态。它包含了操作系统中的“就绪”和“运行”两种状态。线程可能正在CPU上执行，也可能在等待CPU调度。
3. **BLOCKED（阻塞）**：线程等待获取一个监视器锁（synchronized 块或方法）。
4. **WAITING（无限期等待）**：线程等待另一个线程执行特定操作。由以下方法触发：

- Object.wait() (无超时)
- Thread.join() (无超时)
- LockSupport.park()

1. **TIMED_WAITING（限期等待）**：与 WAITING 类似，但有时间限制，超时后会自动返回。由以下方法触发：

- Thread.sleep(long millis)
- Object.wait(long millis)
- Thread.join(long millis)
- LockSupport.parkNanos() / parkUntil()

1. **TERMINATED（终止）**：run() 方法执行完毕或因异常退出。

### sleep 和 wait的区别是什么？

sleep不释放锁，wait释放锁

### sleep会释放cpu吗？

**会。**调用Thread.sleep()的线程会进入TIMED_WAITING状态，它会**让出CPU执行权**，操作系统的调度器会去调度其他处于RUNNABLE状态的线程来执行。但是，它**不会释放它已经持有的任何监视器锁（monitor lock）**。

### blocked和waiting有啥区别

- blocked 为抢锁失败而阻塞。在锁释放后自动变为runnable参与竞争
- wait 为线程**主动调用**了Object.wait(), Thread.join()等方法，放弃CPU执行权，进入阻塞队列，等待唤醒

### wait 状态下的线程如何进行恢复到 running 状态？

被其他线程唤醒，转为blocked。等待锁释放，竞争成功后，恢复为running。

### notify 和 notifyAII 的区别？

随机唤醒一个和全部唤醒

绝大多数情况下选择 notifyAll

### notify 选择哪个线程？

随机选择线程

### 不同的线程之间如何通信？

**“共享内存”** 和 **“同步协作”**

- 可见性
- 有序性和同步

### 线程间通信方式有哪些？

1. **volatile****和****synchronized****关键字（共享内存模型）**

- **volatile**：保证共享变量的**可见性**。当一个线程修改了 volatile 变量，该修改会立即对其他线程可见。它是一种轻量级的通信方式，常用于状态标志的传递（如停止标志）。
- **synchronized****结合****wait()\****,** **notify()\****,** **notifyAll()**：这是最经典的线程协作机制。一个线程通过 synchronized 获取锁，如果条件不满足，就调用 wait() 释放锁并进入等待状态。另一个线程在满足条件后，获取同一个锁，并调用 notify() 或 notifyAll() 来唤醒等待的线程。这同时解决了数据交换（通过共享变量）和状态通知的问题。

1. **Lock****和****Condition****接口（\****java.util.concurrent包）**

- 这是 synchronized 和 wait/notify 的升级版。Lock 提供了更灵活的锁定，而 Condition 接口提供了 await(), signal(), signalAll() 方法，功能与 wait/notify 类似。
- **优点**：一个 Lock可以关联多个 Condition 对象，可以实现更精细的线程等待和唤醒控制（例如，在生产者-消费者模型中，可以为“队列不为空”和“队列不满”创建两个不同的 Condition）。

1. **阻塞队列（\****BlockingQueue）**

- **强烈推荐的高级方式**。java.util.concurrent包提供了多种BlockingQueue的实现（如ArrayBlockingQueue, LinkedBlockingQueue）。
- 它本身就是一个线程安全的容器，内部封装了 wait/notify 或 Lock/Condition 的复杂逻辑。
- 生产者线程调用 put() 方法放入元素，如果队列已满，线程会自动阻塞；消费者线程调用 take() 方法取出元素，如果队列为空，线程会自动阻塞。
- 这使得生产者和消费者完全解耦，代码极其简洁和清晰。

1. **管道流（\****PipedInputStream** **/****PipedOutputStream\****）**

- 用于在两个线程之间直接传递字节流数据。一个线程通过 PipedOutputStream 写入数据，另一个线程通过配对的 PipedInputStream 读取数据。如果缓冲区为空，读线程会阻塞；如果缓冲区已满，写线程会阻塞。

1. **Thread.join()****方法**

- 一种简单的单向通信。如果线程A的代码中调用了 threadB.join()，那么线程A会阻塞，直到线程B执行完毕。这相当于线程B向线程A发送了一个“我已经结束”的信号。

1. **CountDownLatch****和****CyclicBarrier**

- **CountDownLatch**：一个或多个线程等待其他一组线程完成操作。它像一个倒数计数器，一个线程可以调用 await() 等待计数器归零，其他线程通过 countDown() 使计数器减一。
- **CyclicBarrier**：让一组线程互相等待，直到所有线程都到达一个公共的“屏障点”，然后所有线程再一起继续执行。它是可重用的。

### 如何停止一个线程？

- **使用****volatile****标志位**
- **使用****Thread.interrupt()****机制（推荐）**

# 并发安全

### juc包下你常用的类？

java.util.concurrent (JUC) 是Java并发编程的核心工具包。我常用的类可以分为几类：

- **锁（Locks）**:

- ReentrantLock: 可重入互斥锁，功能比 synchronized 更强大。
- ReadWriteLock: 读写锁，允许多个读线程同时访问，但写线程独占，适用于读多写少的场景。ReentrantReadWriteLock 是其实现。

- **原子类（Atomics）**:

- AtomicInteger, AtomicLong, AtomicBoolean 等，通过CAS操作实现无锁的原子性更新，性能高。

- **并发集合（Concurrent Collections）**:

- ConcurrentHashMap: 线程安全的HashMap，通过分段锁或CAS实现高并发。
- CopyOnWriteArrayList: 线程安全的List，写操作时复制整个底层数组，适用于读多写少的场景。
- BlockingQueue: 阻塞队列，如 ArrayBlockingQueue, LinkedBlockingQueue，是生产者-消费者模式的利器。

- **同步工具（Synchronizers）**:

- CountDownLatch: 倒计时门闩。允许一个或多个线程等待其他线程完成一组操作。
- CyclicBarrier: 循环栅栏。让一组线程互相等待，直到所有线程都到达一个共同的屏障点，然后可以继续执行或进行下一轮。
- Semaphore: 信号量。控制同时访问特定资源的线程数量，常用于流量控制。

- **执行器和线程池（Executors）**:

- ExecutorService, ThreadPoolExecutor, Executors 工厂类：用于管理线程池，避免频繁创建和销毁线程带来的开销。

### 怎么保证多线程安全？

保证多线程安全通常有以下几种策略：

1. **同步和加锁**：

- 使用 synchronized 关键字或 java.util.concurrent.locks 包中的锁（如 ReentrantLock）来保护临界区，确保同一时间只有一个线程能访问共享资源。这是最经典的方法。

1. **原子操作**：

- 对于简单的计数、状态更新等操作，使用 java.util.concurrent.atomic 包下的原子类，它们利用CPU的CAS指令实现高效的无锁线程安全。

1. **使用线程安全的数据结构**：

- 使用 JUC 包提供的并发容器，如 ConcurrentHashMap, CopyOnWriteArrayList, BlockingQueue 等。这些类内部已经处理好了并发问题。

1. **不可变性（Immutability）**：

- 如果一个对象创建后其状态就不能被修改，那么它就是不可变的，因而是天然线程安全的。String 和包装类（Integer 等）都是典型的例子。可以自定义不可变对象（所有字段都是 final 且私有）。

1. **线程本地存储（ThreadLocal）**：

- 通过 ThreadLocal 为每个线程提供变量的独立副本，从而避免了线程间的共享和竞争。每个线程操作的都是自己的变量，互不干扰。

### Java中有哪些常用的锁，在什么场景下使用？

- **synchronized**

- **类型**：JVM内置的监视器锁（Monitor Lock）。
- **场景**：最常用，语法简单。适用于并发度不高、同步代码块执行时间短的场景。在JDK 1.6后经过锁升级优化，性能已经非常好。当你不需要 ReentrantLock 的高级功能时，synchronized 是首选。

- **ReentrantLock****(可重入锁)**

- **类型**：JUC包中的API锁。
- **场景**：需要比 synchronized 更高级的功能时使用。

1. **公平性选择**：可以创建公平锁或非公平锁。
2. **可中断的锁获取**：lockInterruptibly() 允许在等待锁时响应中断。
3. **尝试获取锁**：tryLock() 可以立即返回或在指定时间内尝试获取锁，避免死等。
4. **Condition对象**：可以绑定多个 Condition 对象，实现分组唤醒，比 wait/notify 更灵活。

- **ReentrantReadWriteLock****(读写锁)**

- **类型**：读写分离锁。
- **场景**：**读多写少**的场景。多个线程可以同时持有读锁，但写锁是独占的。这可以大大提高并发读的性能。例如，缓存系统的数据读取。

- **StampedLock****(戳锁/票据锁)**

- **类型**：JDK 8引入的更高级的读写锁。
- **场景**：对性能要求极高的读多写少场景。它提供了一种**乐观读锁**。在读的时候不加锁，直接读取，然后校验“戳”（stamp）是否被修改过。如果没被修改，就免去了一次加锁开销；如果被修改，再升级为悲观读锁。

### 怎么在实践中用锁的？

### Java 并发工具你知道哪些？

这个问题的答案与 JUC 包常用类高度重叠，但可以从“工具”的角度来组织：

1. **线程池**：ExecutorService, ThreadPoolExecutor - 管理线程生命周期。
2. **同步控制器**：CountDownLatch, CyclicBarrier, Semaphore -协调线程间的同步与协作。
3. **并发集合**：ConcurrentHashMap, CopyOnWriteArrayList, BlockingQueue - 提供线程安全的数据存储。
4. **锁机制**：ReentrantLock, ReadWriteLock, StampedLock - 控制对共享资源的访问。
5. **原子变量**：AtomicInteger, AtomicReference - 实现无锁的原子更新。
6. **Fork/Join框架**：ForkJoinPool - 用于执行可以分解成小任务的大任务，利用工作窃取算法提高CPU利用率。
7. **Future****和****CompletableFuture**：用于处理异步计算的结果。CompletableFuture（JDK 8+）功能更强大，支持流式API和回调。

### CountDownLatch 是做什么的讲一讲？

CountDownLatch是一个同步辅助类，它允许一个或多个线程一直等待，直到其他线程的操作执行完毕。

- **构造**：CountDownLatch latch = new CountDownLatch(N); 创建时需要指定一个计数值N。
- **核心方法**：

- latch.await();: 调用这个方法的线程会被阻塞，直到计数值减为0。
- latch.countDown();: 将计数值减1。

**典型应用场景：**

1. **主线程等待所有子任务完成**：主线程启动N个子线程去执行任务，然后调用latch.await()。每个子线程完成任务后调用latch.countDown()。当所有子线程都完成后，主线程从await()中唤醒，继续执行汇总等工作。
2. **实现最大并行性**：多个线程在开始执行任务前，都先调用latch.await()。主线程在所有线程都准备好后，调用一次countDown()（如果N=1），所有线程会同时被唤醒，开始执行，达到“同时起跑”的效果。

### synchronized#reentrantlock及其应用场景？

**synchronized**

- **本质**：JVM层面实现的关键字，基于Monitor对象。
- **优点**：使用简单，不易出错，JVM自动管理锁的获取和释放。经过优化后性能良好。
- **缺点**：功能单一，不够灵活。锁的获取和释放是固定的，无法中断，无法超时，一个锁只有一个等待队列。
- **应用场景**：常规的同步需求，代码简洁性优先，且不需要高级功能时。

**ReentrantLock**

- **本质**：API层面的类，java.util.concurrent.locks.Lock 接口的实现。
- **优点**：

- 可选择公平/非公平。
- 可中断地获取锁 (lockInterruptibly)。
- 可超时地获取锁 (tryLock)。
- 可绑定多个Condition，实现精确唤醒。

- **缺点**：使用更复杂，必须手动在 finally 块中释放锁，否则可能导致死锁。
- **应用场景**：需要上述高级功能，或者对锁的控制有更精细化要求的复杂并发场景。

### 除了用synchronized，还有什么方法可以实现线程同步？

1. **java.util.concurrent.locks.Lock****接口**：最直接的替代品，如 ReentrantLock。 2ar. **volatile****关键字**：用于保证变量的**可见性**，可以实现轻量级的同步，但不能保证原子性。适用于“一写多读”且写操作不依赖于当前值的场景。
2. **原子类**：使用 AtomicInteger 等原子类，它们通过CAS操作保证了复合操作（如 i++）的原子性。 4ar. **ThreadLocal**：通过空间换时间，为每个线程提供独立的变量副本，避免共享，从而根本上避免了同步问题。
3. **JUC同步工具**：CountDownLatch, Semaphore 等也可以用于线程间的同步和协作。

### synchronized锁静态方法和普通方法区别？

**核心区别在于锁的对象不同**：

- **锁普通方法**（实例方法）：锁的是**当前对象实例**（this）。如果多个线程访问同一个对象的 synchronized 方法，它们会互斥。但如果它们访问的是不同对象的 synchronized 方法，则不会互斥。
- **锁静态方法**：锁的是**当前类的Class对象** (YourClass.class)。由于一个类的Class对象在JVM中是唯一的，所以无论多少个线程、通过多少个不同的实例来调用这个静态同步方法，它们都会互斥。

**结论**：锁静态方法影响范围更广，会锁住所有实例对该静态方法的调用。锁普通方法只锁住当前实例。这两种锁互不影响。

### synchronized#reentrantlock区别？

| **特性**          | **synchronized**                            | **ReentrantLock**                       |
| ----------------- | ------------------------------------------- | --------------------------------------- |
| **实现机制**      | JVM内置关键字，基于Monitor                  | JDK提供的API，基于AQS                   |
| **可重入性**      | **都是可重入的**                            | **都是可重入的**                        |
| **锁的获取/释放** | 自动获取和释放，隐式                        | 手动获取和释放，必须在finally中unlock() |
| **公平性**        | **非公平锁**                                | 默认**非公平**，但可设置为**公平锁**    |
| **功能灵活性**    | 功能单一                                    | 功能丰富                                |
| **中断等待**      | 不可中断                                    | 可中断 (lockInterruptibly)              |
| **尝试获取**      | 不支持                                      | 支持 (tryLock)                          |
| **Condition**     | 只有一个等待集 (wait/notify)                | 可绑定多个Condition，精确唤醒           |
| **性能**          | JDK1.6后引入锁升级，性能与ReentrantLock相当 | 在高竞争下性能可能略好，但差异不明显    |

### 怎么理解可重入锁？

**可重入锁**（Reentrant Lock），也叫递归锁，指的是**同一个线程在外层方法获取锁之后，进入该线程的内层方法时，可以再次自动获取该锁，而不会因为之前已经持有锁而产生死锁**。

**原理**： 锁内部维护一个**计数器**和一个**持有锁的线程**引用。

- 当一个线程第一次获取锁时，计数器变为1，并记录下该线程。
- 当该线程再次（重入）获取这个锁时，只需将计数器加1。
- 当线程释放锁时，计数器减1。
- 只有当计数器减到0时，锁才真正被释放，其他线程才能获取。

synchronized 和 ReentrantLock 都是可重入锁。

### synchronized 支持重入吗？如何实现的？

**支持。**

synchronized 是可重入的。它的实现是基于JVM的**Monitor（监视器）机制**。每个Java对象都可以作为一个锁，这个锁关联一个Monitor。Monitor内部有两个关键数据：

1. 一个**计数器 (recursion counter)**。
2. 一个指向**持有该锁的线程 (owner)** 的指针。

**实现过程**：

1. 当一个线程尝试获取一个对象的锁时，如果锁是自由的，JVM会记录下该线程为owner，并将计数器设为1。
2. 如果该线程**再次**尝试获取这个锁，JVM会检查owner是不是当前线程。如果是，就简单地将计数器加1。 3ar. 当线程退出一个synchronized块/方法时，计数器减1。 4ar. 当计数器变为0时，锁被完全释放，owner指针被清空，其他线程可以竞争该锁。

### syncronized锁升级的过程讲一下

**Java对象结构**

- 对象头

- Markword 8字节
- 类型指针 4字节
- 数组长度（只有数组对象存在）

- 对象体
- 对齐填充 （java对象一定为8字节倍数）

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764150345660-dfd9f151-e6df-4255-8e51-61c9a353a3c5.png)

static属性，不属于对象体内容，属于类本身。开启压缩指针情况下，类型指针和对象引用指针为4字节，反之为8字节。

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764150345565-b5b6f2d6-46f7-4d08-822a-399a682ea211.png)

从JVM指令层看，`synchronized` 可以被分为两种实现情况：

1. **同步代码块**：JVM使用 monitorenter 和 monitorexit 这两个指令来实现。当执行 monitorenter 时，线程尝试获取对象的 **Monitor** 的所有权。monitorexit 则释放所有权。编译器会确保在代码块正常结束和异常结束时都调用 monitorexit。
2. **同步方法**：通过方法元信息中的 ACC_SYNCHRONIZED 访问标志来实现的。当方法被调用时，JVM会检查这个标志，如果是同步方法，执行线程就会先获取对象的Monitor，执行完毕后再释放。

**Monitor** 可以理解为每个对象都关联的一个监视器锁，它才是synchronized重量级锁的真正实现。

**不同的加锁时间点，决定了不同的锁控制粒度和灵活性，从而影响了程序的并发性能。**

锁消息存储在java对象头的Markword中，

1. **无锁状态**：对象刚被创建，还没有任何线程尝试获取它的锁。
2. **偏向锁**：

- 总是同一线程持有锁
- **过程**：偏向锁标识位置为1，cas 使 MarkWord 记录当前线程id。再次进入代码块，检验线程id。
- **升级时机**：有另一个线程竞争锁。
- 缺点：频繁撤销和升级，造成性能负担，在jdk15后默认关闭

1. **轻量级锁**：

- 少量竞争，无需阻塞，自旋获取
- **过程**：线程在自己的**栈帧中创建Lock Record**，然后用CAS尝试将对象头的Mark Word更新为指向这个Lock Record的指针。成功，获取锁，失败，自旋获取。
- **升级时机**：自旋一定次数，其他线程竞争

1. **重量级锁**：

- 大量竞争，阻塞
- **过程**：MarkWord指向Monitor对象，所有线程进入阻塞，释放锁时,唤醒线程抢锁。
   

### JVM对Synchornized的优化？

除了**锁升级（偏向锁 -> 轻量级锁 -> 重量级锁）**，JVM还对synchronized做了其他优化，以减少其性能开销：

1. **自旋锁与自适应自旋（Spin-locking & Adaptive Spinning）**

- **自旋锁**：当一个线程尝试获取锁但失败时，它不会立即被挂起（挂起和唤醒线程涉及操作系统内核，开销大），而是执行一个忙循环（“自旋”），看看持有锁的线程是否会很快释放锁。这对于锁占用时间非常短的场景非常有效。
- **自适应自旋**：自旋的次数不是固定的。JVM会根据上一次自旋的成功率和锁持有者的状态来动态调整自旋的次数。如果对于某个锁，自旋很少成功，那么下次获取该锁时就可能直接跳过自旋，避免浪费CPU。

1. **锁消除（Lock Elimination）**

- **原理**：JIT（即时编译器）在运行时，会分析代码，如果它检测到某个对象锁不可能被其他线程访问到（比如，这个对象是一个局部变量，其生命周期只在当前线程的方法栈内），那么JIT就会**消除**这个锁。
- **例子**：在一个方法内部创建StringBuffer并进行append操作。StringBuffer的方法是同步的，但如果这个StringBuffer对象没有被传出去，它就是线程私有的，加锁是完全不必要的。JIT会把这个锁去掉。

1. **锁粗化（Lock Coarsening）**

- **原理**：如果一系列连续的操作都对同一个对象反复加锁和解锁，JIT编译器可能会将这些加锁操作**合并**成一个更大范围的锁，以减少频繁加锁和解锁带来的开销。
- **例子**：在一个循环中反复调用 vector.add()。JIT可能会把锁的范围扩大到整个循环之外，只加一次锁，而不是每次循环都加锁解锁。

### 介绍一下AQS

**AbstractQueuedSynchronizer****(AQS)** 是JUC包中构建锁和同步器的**核心框架**。ReentrantLock, Semaphore, CountDownLatch 等都是基于AQS实现的。

**AQS的核心思想**： 它内部维护了一个**state变量（一个volatile int）**和一个**FIFO双向队列（CLH队列）**。

- **state\****变量**：代表同步状态。子类可以根据自己的需求来定义state的含义。比如，在ReentrantLock中，state=0表示锁未被持有，state>0表示锁被持有的重入次数。在Semaphore中，state表示剩余的许可数量。
- **CLH队列**：用于存放所有**获取同步状态失败**而被阻塞的线程。当一个线程请求锁失败后，AQS会将其封装成一个Node节点，加入到队列的尾部，并将其挂起（park）。

AQS提供了两类核心操作的模板方法，需要子类去实现：

- **独占模式**：tryAcquire(int) 和 tryRelease(int)。用于实现独占锁，如ReentrantLock。
- **共享模式**：tryAcquireShared(int) 和 tryReleaseShared(int)。用于实现共享型同步器，如Semaphore和CountDownLatch。

当一个线程释放锁时（release），它会修改state，并唤醒（unpark）队列头部的下一个等待线程。

### CAS 和 AQS 有什么关系？

**一句话总结：AQS是基于CAS实现的。**

- **CAS (Compare-And-Swap)**：是CPU层面提供的一条**原子指令**。它是一种无锁算法，用于实现多线程环境下的原子性操作。它包含三个操作数——内存位置V、预期原值A和新值B。当且仅当内存位置V的值与预期原值A相同时，处理器才会将该位置的值更新为新值B，否则不做任何操作。这个过程是原子的。
- **AQS (AbstractQueuedSynchronizer)**：是JUC包中构建锁和同步器的**核心框架**。ReentrantLock, CountDownLatch, Semaphore等都是基于AQS实现的。

**关系**： AQS内部有一个核心的状态变量 private volatile int state;。所有对这个状态的修改，比如获取锁（state从0变1）和释放锁（state从1变0），都是通过**CAS**操作来完成的。

- 当一个线程想获取锁时，AQS会使用CAS尝试将state从0修改为1。
- 如果成功，线程就获得了锁。
- 如果失败，说明锁已被其他线程持有。AQS就会将该线程放入一个等待队列中。

所以，**CAS是AQS实现原子性状态更新的基石**，而AQS则是在CAS的基础上，提供了线程排队、阻塞、唤醒等一整套复杂的上层逻辑。

### 如何用AQS 实现一个可重入的公平锁？

实现一个自定义锁需要继承 AQS 并重写其指定的方法。

```plain
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.Lock;

public class MyReentrantFairLock implements Lock {

    // 内部类，公平同步器的实现
    private static class FairSync extends AbstractQueuedSynchronizer {

        // 尝试获取锁
        @Override
        protected boolean tryAcquire(int acquires) {
            final Thread current = Thread.currentThread();
            int c = getState(); // 获取当前锁的状态（重入次数）

            if (c == 0) { // 锁是自由的
                // 公平性的关键：检查等待队列中是否有比我更早的线程
                if (!hasQueuedPredecessors() && compareAndSetState(0, acquires)) {
                    // 如果没有前驱节点，并且通过CAS成功获取锁
                    setExclusiveOwnerThread(current); // 设置当前线程为锁的持有者
                    return true;
                }
            } else if (current == getExclusiveOwnerThread()) { // 锁已被持有，检查是否是当前线程（可重入）
                int nextc = c + acquires;
                if (nextc < 0) throw new Error("Maximum lock count exceeded");
                setState(nextc); // 直接增加state，无需CAS，因为已持有锁
                return true;
            }
            return false; // 获取锁失败
        }

        // 尝试释放锁
        @Override
        protected boolean tryRelease(int releases) {
            int c = getState() - releases;
            if (Thread.currentThread() != getExclusiveOwnerThread()) {
                throw new IllegalMonitorStateException();
            }
            boolean free = false;
            if (c == 0) { // 如果state减到0，完全释放锁
                free = true;
                setExclusiveOwnerThread(null);
            }
            setState(c); // 设置state
            return free;
        }

        // 是否被独占持有
        @Override
        protected boolean isHeldExclusively() {
            return getExclusiveOwnerThread() == Thread.currentThread();
        }

        // 提供Condition支持
        Condition newCondition() {
            return new ConditionObject();
        }
    }

    private final FairSync sync = new FairSync();

    // Lock接口的实现，全部委托给内部的Sync对象
    @Override
    public void lock() {
        sync.acquire(1);
    }

    @Override
    public void unlock() {
        sync.release(1);
    }

    // ... 其他Lock接口方法的实现，都委托给sync ...
    @Override
    public void lockInterruptibly() throws InterruptedException { sync.acquireInterruptibly(1); }
    @Override
    public boolean tryLock() { return sync.tryAcquire(1); }
    @Override
    public boolean tryLock(long time, TimeUnit unit) throws InterruptedException { return sync.tryAcquireNanos(1, unit.toNanos(time)); }
    @Override
    public Condition newCondition() { return sync.newCondition(); }
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321679-2080ff8e-d818-4a4e-b05b-f922d1c8a952.gif)

**关键点**：

1. **state**：AQS的state被用来表示**重入的次数**。
2. **可重入实现**：在tryAcquire中，如果state > 0，检查当前线程是否就是锁的持有者，如果是，就简单地增加state。
3. **公平性实现**：在tryAcquire中，当state == 0时（锁是自由的），先调用hasQueuedPredecessors()检查等待队列中是否有其他线程。如果有，就返回false，让当前线程去排队，以此保证了**先来后到**的公平性。

### Threadlocal作用，原理，具体里面存的key value是啥，会有什么问题，如何解决？

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764163111562-808564dc-4bb6-407c-9b50-64a2036ddea4.png)

**每个 Thread 都有自己独立的 ThreadLocalMap，Map 的 key 是 ThreadLocal 对象本身。**

- 每个 Thread 都可以持有多个 ThreadLocal 变量
- 每个 ThreadLocal 在每个 Thread 中都有独立的 value
- 不同线程之间互不影响、互不可见

- **会有什么问题**： **内存泄漏（Memory Leak）**。

```java
static class Entry extends WeakReference<ThreadLocal<?>> {
    Object value;
}
```

- key（ThreadLocal）是弱引用，value 是强引用

- 当外部不再有对ThreadLocal对象的强引用时，GC会回收这个ThreadLocal对象。
- 此时，ThreadLocalMap中对应Entry的**Key**会变成null（因为是弱引用）。
- 但是，它的**Value**仍然被Entry强引用着，并且这个Entry本身还被ThreadLocalMap强引用，ThreadLocalMap又被Thread强引用。
- 如果这个线程是一个**长生命周期的线程（比如线程池中的线程）**，那么这个Key为null的Entry及其强引用的Value就永远不会被回收，造成了内存泄漏。

- **如何解决**： **最佳实践**：在使用完ThreadLocal后，总是在finally块中调用 threadLocal.remove() 方法。remove()方法会主动将ThreadLocalMap中对应的Entry移除，从而让Key和Value都能被GC回收。

```plain
ThreadLocal<MyObject> myThreadLocal = new ThreadLocal<>();
try {
    myThreadLocal.set(new MyObject());
    // ... use myThreadLocal ...
} finally {
    myThreadLocal.remove(); // 必须执行此操作！
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321899-1eb89bc8-66a7-457d-afec-63881ed9d1fd.gif)

### 这是一个思想上的区别，而不是具体的锁。

- **悲观锁（Pessimistic Locking）**

- **思想**：总是假设最坏的情况，认为数据在任何时候都可能被其他线程修改。所以，在每次对数据进行操作之前，都会先**加锁**，操作完成后再**解锁**。其他线程在此期间会被阻塞。
- **优点**：数据一致性强，实现简单。
- **缺点**：并发性能差，线程阻塞和唤醒的开销大。
- **Java实现**：synchronized、ReentrantLock等都是悲观锁的体现。

- **乐观锁（Optimistic Locking）**

- **思想**：总是假设最好的情况，认为数据在一般情况下不会产生冲突。所以，操作数据时不加锁。在**提交更新**的时候，会去**检查**在此期间数据是否被其他线程修改过。
- 如果没被修改，更新成功。
- 如果被修改，更新失败，然后通常会进行重试（自旋）、报错或放弃。
- **优点**：避免了线程阻塞，在高并发的读多写少场景下性能非常好。
- **缺点**：在写操作频繁、冲突严重的场景下，反复重试会消耗大量CPU资源，性能反而下降。
- **Java实现**：**CAS（Compare-And-Swap）**是乐观锁的核心思想。java.util.concurrent.atomic包下的原子类都是基于CAS实现的。



### Java中想实现一个乐观锁，都有哪些方式？

1. **CAS（Compare-And-Swap）机制**： 这是最底层、最常见的实现方式。直接使用JUC包提供的原子类。

```plain
AtomicInteger atomicInt = new AtomicInteger(0);
// 模拟更新操作
atomicInt.compareAndSet(0, 1); // 如果当前值是0，就更新为1
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321882-d4425286-e0dc-4253-bd68-333311b33c8a.gif)

1. **版本号机制（Versioning）**： 这在数据库中非常常用，也可以在Java代码中模拟。

- 给数据增加一个版本号字段，如 version。
- 读取数据时，连同 version 一起读出。
- 更新数据时，必须检查当前数据库中的 version 是否与你之前读到的一致。

- SQL: UPDATE table SET data = newData, version = version + 1 WHERE id = ? AND version = oldVersion;

- 如果UPDATE影响的行数为0，说明在你操作期间，数据已经被其他线程修改（version不匹配），更新失败。

### CAS 有什么缺点？为什么不能所有的锁都用CAS?

**CAS的缺点：**

1. **ABA问题**：

- **描述**：一个值原来是A，被另一个线程改成了B，然后又改回了A。此时，CAS检查时发现值仍然是A，就会认为它没有被修改过，从而执行更新。但在某些场景下，这个中间状态的改变是需要被感知的。
- **解决**：使用**带版本号的原子引用**，如 AtomicStampedReference。它将值和版本号（stamp）绑定在一起，CAS时不仅比较值，还比较版本号。

1. **自旋开销大**：

- 如果锁的竞争非常激烈，CAS操作会频繁失败并进入自旋。这会持续占用CPU资源，造成性能浪费。相比之下，synchronized这类重量级锁会使线程进入阻塞状态，让出CPU。

1. **只能保证一个共享变量的原子操作**：

- CAS一次只能对一个内存地址的值进行原子操作。如果需要同时保证多个变量的原子性，CAS就无能为力了。
- **解决**：可以将多个变量封装成一个对象，然后使用 AtomicReference 来对这个对象的引用进行CAS操作。

**为什么不能都用CAS？**

- **适用场景不同**：CAS适用于**竞争不激烈、锁占用时间短**的场景。在这种情况下，自旋的成本低于线程的阻塞和唤醒。
- **高竞争场景下的性能问题**：在高竞争下，大量线程自旋会空耗CPU，性能急剧下降，甚至不如让线程阻塞的synchronized。
- **功能限制**：CAS本身无法实现synchronized或ReentrantLock那样复杂的功能，如公平性、可重入、Condition等待/通知机制等。这些复杂的同步器（如AQS）虽然基于CAS，但它们增加了大量的逻辑（如等待队列）来弥补CAS本身的不足。

### CAS 有什么问题，Java是怎么解决的？

1. **问题：ABA问题**

- **Java解决方案**：使用 java.util.concurrent.atomic.AtomicStampedReference。它在CAS时会同时检查当前值和当前的版本戳（stamp），只有两者都符合预期时才更新，并且更新时会同时更新值和版本戳。

1. **问题：高竞争下的自旋消耗CPU**

- **Java解决方案**：这不是一个能被"解决"的问题，而是一个场景选择问题。Java提供了不同的锁机制让你选择：

- 在低竞争场景，原子类（CAS）是高效的。
- 在高竞争场景，应选择synchronized或ReentrantLock，它们会将线程挂起，节约CPU。
- JVM的**自适应自旋**也在一定程度上缓解了这个问题。

1. **问题：只能操作一个变量**

- **Java解决方案**：使用java.util.concurrent.atomic.AtomicReference。将多个变量封装到一个对象中，然后通过AtomicReference对该对象的引用进行原子更新。

------

### 24. volatile关键字有什么作用？

volatile是Java虚拟机提供的**最轻量级的同步机制**。它主要有两个作用：

1. **保证可见性（Visibility）**： 当一个线程修改了一个volatile变量的值，这个新值对其他线程是**立即可见**的。它会强制将修改后的值立即写回主内存，并让其他线程工作内存中该变量的缓存失效，从而需要重新从主内存读取。
2. **禁止指令重排序（Ordering）**： volatile会通过插入**内存屏障（Memory Barrier）\****来防止编译器和处理器对其前后的指令进行重排序优化，从而保证了一定程度的有序性。这在某些特定场景下至关重要，比如著名的双重检查锁定（Double-Checked Locking）单例模式**。

### 25. 指令重排序的原理是什么？

**原理**：为了提高处理器的执行效率和性能，**编译器**和**处理器**在不改变**单线程程序执行结果**的前提下，可以对输入的代码指令进行重新排序和优化。

**为什么需要重排序？** 现代CPU采用流水线技术执行指令（取指、译码、执行、访存、写回）。如果指令之间没有依赖关系，重排序可以让流水线更加饱满，避免因等待某个操作（如内存读取）而产生的停顿，从而提高CPU吞吐率。

**重排序的种类**：

1. **编译器优化重排序**：编译器在不改变单线程语义的前提下，可以重新安排语句的执行顺序。
2. **指令级并行重排序**：现代处理器采用指令级并行技术，可以将多条指令重叠执行。如果不存在数据依赖性，处理器可以改变语句对应机器指令的执行顺序。
3. **内存系统重排序**：由于处理器使用缓存和读/写缓冲区，这使得加载和存储操作看上去可能是在乱序执行。

**带来的问题**： 在单线程环境下，重排序不会出问题（as-if-serial语义保证）。但在多线程环境下，一个线程的重排序可能会对另一个线程产生不可预期的影响，破坏可见性和有序性。这就是volatile和synchronized需要解决的问题。

### 26. volatile可以保证线程安全吗？

**不一定。它不能完全保证线程安全。**

- volatile 保证了**可见性**和**有序性**。
- 但是，它**不保证原子性**。

**例子**： 经典的 count++ 操作。

```plain
volatile int count = 0;

// 线程A和线程B同时执行
count++;
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1763993321881-67bcfa8d-bd3a-4244-b4be-69d8013f059b.gif)

count++ 实际上包含三个步骤：

1. 读取 count 的值。
2. 将值加1。
3. 将新值写回 count。

即使 count 是 volatile 的，也可能发生以下情况：

1. 线程A读取 count 的值为0。
2. 此时CPU切换，线程B读取 count 的值，由于A还没有写回，B读到的也是0。
3. 线程B执行加1，将1写回 count。
4. CPU切换回线程A，A根据它之前读到的0执行加1，也将1写回 count。

最终结果是1，但我们期望的是2。这就是**原子性**被破坏了。

**结论**：只有当一个变量的写操作不依赖于其当前值时（如布尔标志位），或者能确保只有一个线程在修改它时，volatile才能保证线程安全。对于复合操作，必须使用 synchronized 或 Atomic 原子类。

### 27. volatile 和 synchronized 的区别？

| **特性**       | **volatile**                                 | **synchronized**                       |
| -------------- | -------------------------------------------- | -------------------------------------- |
| **本质**       | 变量修饰符，轻量级                           | 关键字，可修饰方法或代码块，重量级     |
| **保证的特性** | **可见性**、**有序性**                       | **可见性**、**有序性**、**原子性**     |
| **是否阻塞**   | **不阻塞**线程                               | 会**阻塞**其他试图获取同一锁的线程     |
| **作用范围**   | 只能作用于**变量**                           | 可以作用于**代码块**和**方法**         |
| **编译器优化** | 禁止指令重排序                               | 同样具有禁止重排序的效果               |
| **使用场景**   | 适用于状态标志、双重检查锁定等轻量级同步场景 | 适用于保护临界区，保证复合操作的原子性 |

### 28. 什么是公平锁和非公平锁？

- **公平锁（Fair Lock）**： 遵循**先来后到（FIFO）**的原则。线程获取锁的顺序按照它们发出请求的顺序。等待时间最长的线程将优先获得锁。

- **优点**：所有线程都能得到执行机会，不会产生饥饿现象。
- **缺点**：吞吐量较低，因为需要维护一个有序队列，并且线程切换开销大。

- **非公平锁（Non-fair Lock）**： 允许“插队”。当锁被释放时，任何一个正在请求锁的线程（无论是刚来的还是已在队列中等待的）都有机会获得锁。

- **优点**：吞吐量更高，因为减少了线程上下文切换的开销。
- **缺点**：可能导致某些线程长时间得不到锁，产生**饥饿（Starvation）**现象。

### 29. 非公平锁吞吐量为什么比公平锁大？

**核心原因：减少了线程上下文切换的开销。不同线程之间的切换**

设想一个场景：

- 线程A持有锁，线程B在等待队列中等待。
- 线程A释放了锁。

**在公平锁模式下**：

1. 线程A释放锁后，AQS会唤醒等待队列头部的线程B。
2. 唤醒线程B需要时间，并且涉及从用户态到内核态的转换，即**上下文切换**。
3. 在线程B被完全唤醒之前，如果线程A（或其他新来的线程C）又想立即获取锁，它必须排队，即使锁此刻是空闲的。这造成了CPU的短暂空闲。

**在非公平锁模式下**：

1. 线程A释放锁后，如果它紧接着又想获取锁，它可以**立即尝试**获取。
2. 由于它正在CPU上运行，不需要上下文切换，所以它很可能在线程B被唤醒之前就再次拿到了锁。
3. 这就**避免了一次昂贵的上下文切换**，CPU一直在工作，没有空闲期。

**结论**：非公平锁通过允许“插队”，减少了线程挂起和唤醒的次数，让CPU尽可能地保持繁忙，从而提高了单位时间内的总任务处理量，即**吞吐量**。

### Synchronized是公平锁吗？

**不是，\****synchronized** **是非公平锁。**

它在锁释放后，允许任何线程（包括新来的线程）竞争锁，没有遵循严格的FIFO队列。

### ReentrantLock是怎么实现公平锁的？

通过其内部的同步器Sync的子类FairSync来实现。

当你创建公平锁时 new ReentrantLock(true)，内部会使用 FairSync。FairSync在尝试获取锁时（tryAcquire方法），会增加一个额外的判断：

!hasQueuedPredecessors()

这个方法会检查AQS的等待队列中，当前线程前面是否还有其他等待的线程。

- 如果**有**（返回true），那么!hasQueuedPredecessors()为false，当前线程获取锁失败，乖乖去队尾排队。
- 如果**没有**（返回false），当前线程才会去尝试用CAS获取锁。

这个小小的检查，就保证了锁的获取严格按照线程请求的顺序，从而实现了公平性。

### 什么情况会产生死锁问题？如何解决？

**死锁（Deadlock）**：指两个或多个线程在执行过程中，因争夺资源而造成的一种互相等待的现象，若无外力干涉，它们都将无法推进下去。

**产生死锁的四个必要条件**（必须同时满足）：

1. **互斥条件（Mutual Exclusion）**：资源在任意时刻只能被一个线程占用。
2. **请求与保持条件（Hold and Wait）**：一个线程因请求资源而阻塞时，对已获得的资源保持不放。
3. **不可剥夺条件（No Preemption）**：线程已获得的资源，在未使用完之前，不能被强行剥夺。
4. **循环等待条件（Circular Wait）**：存在一种头尾相接的循环等待资源关系。例如，线程A等待线程B持有的资源，线程B等待线程A持有的资源。

**如何解决（预防）死锁**： 核心思想是**破坏上述四个必要条件中的一个或多个**。

1. **破坏“请求与保持”条件**：

- **一次性申请所有资源**：线程在运行前，一次性申请所有它需要的资源。如果不能全部获得，就一个也不要，等待一段时间再试。
- **缺点**：降低了资源的利用率，且很难预知一个线程需要的所有资源。

1. **破坏“不可剥夺”条件**：

- **使用带超时的锁**：当一个线程持有部分资源，再去请求其他资源时，如果请求受阻，它可以设置一个超时时间。超时后，如果仍未获得，就主动**释放自己已持有的所有资源**，然后重试。ReentrantLock.tryLock(long timeout, TimeUnit unit)就是很好的工具。

1. **破坏“循环等待”条件（最常用、最有效的方法）**：

- **资源有序申请法**：对所有资源进行排序，所有线程都必须**严格按照相同的顺序**来申请资源。例如，系统中有锁A和锁B，规定所有线程必须先获取锁A，再获取锁B。这样就打破了循环等待的链条。

**如何排查死锁**：

- **jstack****命令**：通过 jps 找到Java进程ID，然后执行 jstack <pid>。jstack会分析线程堆栈，如果存在死锁，它会明确地打印出死锁信息，包括涉及的线程和它们正在等待的锁。
- **可视化工具**：使用JConsole、VisualVM等工具，它们提供了图形化的线程监控和死锁检测功能。