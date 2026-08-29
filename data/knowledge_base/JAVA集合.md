# List 

## ArrayList (动态数组)和 Array(数组)有什么区别？ 

- **大小和自动扩容**

- 数组在创建时必须指定⼤⼩，且⼤⼩是固定的。⼀旦数组被创建，其⼤⼩不能更改。 
- ArrayList是动态数组实现的，它的⼤⼩可以动态增⻓或缩⼩。在不断添加元素时，ArrayList 会⾃动进⾏扩 容。

- **支持泛型**

- 数组可以存储任何类型的元素，但不⽀持泛型。 
- ArrayList：⽀持泛型，可以指定存储的元素类型 

- **存储对象**

- Array 可以直接存储基本类型数据，也可以存储对象。
- ArrayList 中只能存储对象。对于基本类型数据，需要使⽤其对应的包装类（如 Integer、Double 等） 

- **集合功能**

- Array是⼀个简单的数据结构，不提供额外的⽅法来进⾏元素的增删改查操作。 
- ArrayList是集合框架的⼀部分，提供了丰富的⽅法，如添加、删除、查找等。 

## ArrayList 与 LinkedList 的区别? 

- 底层数据结构不同：

ArrayList使用数组实现，通过索引进行快速访问元素。LinkedList使用链表实现，通过节点之间的指针进行元素的访问和操作。

- 插入和删除操作的效率不同：

ArrayList在尾部的插入和删除操作效率较高，但在中间或开头的插入和删除操作效率较低，需要移动元素。LinkedList在任意位置的插入和删除操作效率都比较高，因为只需要调整节点之间的指针，但是LinkedList是不支持随机访问的，所以除了头结点外插入和删除的时间复杂度都是O(n），效率也不是很高所以LinkedList基本没人用。

- 随机访问的效率不同：

ArrayList支持通过索引进行快速随机访问，时间复杂度为O(1)。LinkedList需要从头或尾开始遍历链表，时间复杂度为O(n)。

- 空间占用：

ArrayList在创建时需要分配一段连续的内存空间，因此会占用较大的空间。LinkedList每个节点只需要存储元素和指针，因此相对较小。

- 使用场景：

ArrayList适用于频繁随机访问和尾部的插入删除操作，而LinkedList适用于频繁的中间插入删除操作和不需要随机访问的场景。

- 线程安全：

这两个集合都不是线程安全的，Vector是线程安全的

## 为什么ArrayList不是线程安全的，具体来说是哪里不安全?

在高并发添加数据下，ArrayList会暴露三个问题;

- 部分值为null(我们并没有add null进去)
- 索引越界异常
- size与我们add的数量不符

## 如何解决？

- 使用Collections类的synchronizedList方法将ArrayList包装成线程安全的List:

```java
List<String> synchronizedList = Collections.synchronizedList(arrayList);
```

- 使用 CopyOnWriteArrayList 类代替 ArrayList，它是一个线程安全的 List 实现：

```java
CopyOnWriteArrayList<String> copyOnWriteArrayList = new CopyOnWriteArrayList<>(arrayList);
```

- 使用Vector 类代替 ArrayList，Vector是线程安全的List实现：

```java
Vector<String> vector = new Vector<>(arrayList);
```

### ArrayList的扩容机制 

ArrayList在添加元素时，如果当前元素个数已经达到了内部数组的容量上限，就会触发扩容操作。ArrayList的扩容操作主要包括以下几个步骤：

- 计算新的容量：一般情况下，新的容量会扩大为原容量的1.5倍（在JDK10之后，扩容策略做了调整），然后检查是否超过了最大容量限制。
- 创建新的数组：根据计算得到的新容量，创建一个新的更大的数组。
- 将元素复制：将原来数组中的元素逐个复制到新数组中。
- 更新引用：将ArrayList内部指向原数组的引|用指向新数组。
- 完成扩容：扩容完成后，可以继续添加新元素。

ArrayList的扩容操作涉及到数组的复制和内存的重新分配，所以在频繁添加大量元素时，扩容操作可能会影响性能。为了减少扩容带来的性能损耗，可以在初始化ArrayList时预分配足够大的容量，避免频繁触发扩容操作。

之所以扩容是1.5倍，是因为1.5可以充分利用移位操作，减少浮点数或者运算时间和运算次数。





# Set

## Set集合有什么特点？如何实现key无重复的？

- set集合特点：

Set集合中的元素是唯一的，不会出现重复的元素。

- set实现原理：

Set集合通过内部的数据结构(如哈希表、红黑树等）来实现key的无重复。当向Set集合中插入元素时，会先根据元素的hashCode值来确定元素的存储位置，然后再通过equals方法来判断是否已经存在相同的元素，如果存在则不会再次插入，保证了元素的唯一性。

## 有序的Set是什么？记录插入顺序的集合是什么？

- 有序的Set是TreeSet和LinkedHashSet。TreeSet是基于红黑树实现，保证元素的自然顺序。LinkedHashSet是基于双重链表和哈希表的结合来实现元素的有序存储，保证元素添加的自然顺序
- 记录插入顺序的集合通常指的是LinkedHashSet，它不仅保证元素的唯一性，还可以保持元素的插入顺序。当需要在Set集合中记录元素的插入顺序时，可以选择使用LinkedHashSet来实现。

# Map

### Map接口有那些实现类 ？

Map接⼝有很多实现类，其中⽐较常⽤的有 HashMap、LinkedHashMap、TreeMap、ConcurrentHashMap。

- 对于**不需要排序**的场景，优先考虑使⽤**HashMap**，因为它是**性能最好的Map实现**。如果需要保证**线程安全**，则可 以使⽤**ConcurrentHashMap**。它的性能好于Hashtable，因为它在put时采⽤分段锁/CAS的加锁机制，⽽不是像 Hashtable那样，⽆论是put还是get都做同步处理。 
- 对于**需要排序**的场景，如果需要**按插入顺序排序**则可以使⽤**LinkedHashMap**，如果需要将**key按自然顺序**排列甚⾄ 是**⾃定义顺序排列**，则可以选择**TreeMap**。如果需要保证线程安全，则可以使⽤Collections⼯具类将上述实现类包 装成线程安全的Map。

### Java中的HashMap了解吗？HashMap的底层实现？

- HashMap将数据以键值对的形式存储，是线程不安全的。
- HashMap的底层实现?

- JDK 7中的HashMap使用的是**数组+链表**的实现方式，即**拉链法**。
- 在JDK7版本因为使用了链表，在出现hash冲突时，会在冲突位置形成链表，将新增元素加入到链表中，带来的问题就是在冲突过多的情况下，链表可能会特别长。导致复杂度无限接近于O(N)
- JDK8引I入了**红黑树（Red-BlackTree）**，**链表长度超过8且当前数组长度大于64**时，会将链表转换为红黑树,以提高在链表长度较长时的查找性能。这种结构被称为**树化桶（TreeBins）。**（treeifyBin）

- 总结：Java7使用数组+链表，Java8使用数组+链表或红黑树(链表超过8会转为红黑树，小于6会变成链表)

### 为什么链表大小超过8会自动转为红黑树，小于6时重新变成链表

- 树节点比普通节点要大两倍，当bin有足够多的节点时，才转化为树节点。根据泊松分布，在负载因子默认为0.75的时候，单个hash槽内元素个数为8的概率小于百万分之一，所以将7作为一个分水岭，等于7的时候不转换，大于等于8的时候才转换成红黑树，小于等于6的时候转化为链表。实现空间的时间的权衡。

### 什么是红黑树？

- **左根右**

二叉搜索树

- **根叶黑**

根和叶子节点都是黑色

- **不红红**

不存在连续的两个红色节点

- **黑路同**

任一节点到叶所有黑节点数量相同

### 为什么要引入红黑树，而不用其他树？

 HashMap 使用红黑树是为了提升查询效率，将冲突严重的桶的查询时间从 O(n) 降低到 O(log n)，同时避免 hash 冲突攻击，提高稳定性和安全性。  

- 红黑树旋转次数更少、插入删除更快
- 红黑树追求插入/删除性能+相对平衡
- AVL树更严格平衡，适合查多改少的场景(比如TreeMap)

- 在替换链表时，常用的数据结构是二叉树，但是二叉树一定是左边<rOot根节点<右边。在时间复杂度中从链表的O(N)变成了O(logN)。
- 在极端情况下，会出现左右其中一边无限长。导致退化到链表。基于此情况衍生出平衡二叉树，通过在添加元素，进行左旋、右旋操作维持根节点左右两端的平衡。但是因为为了保证两端的平衡，在数据量较大的插入/删除时，会存在大量的IO开销
- 引入红黑树，是因为红黑树具有以下几点性质

- 不追求绝对的平衡，插入或删除节点时，允许有一定的局部不平衡，相较于AVL树的绝对自平衡，减少了很多性能开销
- 红黑树是一种自平衡的二叉搜索树，因此插入和删除操作的时间复杂度都是o(logn);

- 红黑树和二叉搜索树、AVL树有什么区别？

- 红黑树：节点颜色为红色或黑色，且根节点和叶子节点为黑色；任意一个红色节点的子节点是黑色；插入和删除操作的时间复杂度都是o(logn)；
- 二叉搜索树：在最坏的情况下，二叉搜索树的时间复杂度为O(n)；树不会平衡，不会进行旋转操作，达不到自平衡;
- AVL树：由于AVL树保持平衡性，查找、插入和删除操作的时间复杂度都是o(logn)；插入和删除节点时，会发生旋转操作，达到自平衡

- HashMap会出现红黑树一直增高变成无限高的情况吗？

- 不会无限增高，当链表长度超过8时，链表转换为红黑树，当不足这个阈值时，重新转换为链表。这种动态机制防止了红黑树的无限增长。

- HashMap读和写的时间复杂度是多少?

- 读：

- 在最佳情况下：直接通过数组下标访问数据，O(1);
- 最坏情况下：发生哈希冲突，链表为O(n),红黑树为O(Iogn)。

- 写：O(n)，但是如果所有元素都在一个桶内，则每次插入需要O(n)。

### HashMap底层采用哪种算法计算hash值，还有哪些算法？

底层采用的key的HashCode方法的值结合数据长度进行无符号右移，按位异或，按位与计算出索引（hash&(length - 1)）

还有：平方取中，取余，伪随机数

其他算法效率比较低，位运算效率高

### HashMap的Hash值和索引有什么区别？

在Java的HashMap中，**hash值**和**计算出的索引**是两个相关但不同的概念：

1. **Hash值**：

- 是键（Key）的`hashCode()`经过扰动处理后的结果（如Java 8中对高16位和低16位进行异或操作，以降低哈希冲突概率）。
- 表示键的“唯一性”特征，但不同键的hash值可能相同（哈希冲突）。

1. **索引**：

- 通过将hash值与当前数组长度进行位运算（如`hash & (capacity - 1)`）得到。
- 表示键值对在HashMap底层数组中的存储位置。

### 关键区别：

- **Hash值是全局的**，与数组长度无关；**索引是局部的**，依赖于当前数组长度。
- 索引由hash值推导而来，但相同的索引可能对应不同的hash值。

### 索引相同，hash值可能不同吗？

**是的，可能不同**。例如：

- 数组长度为16时，索引计算为`hash & 15`（二进制`1111`）。
- 若两个键的hash值分别为`17`（`10001`）和`1`（`00001`），它们的索引均为`1`（`17 & 15 = 1`，`1 & 15 = 1`），但hash值不同。

### 结论：

- 索引相同仅表示键值对存储在数组的同一位置（形成链表或红黑树），但它们的hash值可能不同。
- 这是哈希表设计中碰撞处理的典型场景。

### Hash冲突有什么解决方法？HashMap如何解决哈希冲突的？

- 链接法：

使用链表或其他数据结构来存储冲突的键值对，将它们链接在同一个哈希桶

中。

- 开放寻址法：

在哈希表中找到另一个可用的位置来存储冲突的键值对，而不是存储在

链表中。常见的开放寻址方法包括线性探测、二次探测和双重散列。

- 再哈希法(Rehashing)：

当发生冲突时，使用另一个哈希函数再次计算键的哈希值，直到找到一个空槽来存储键值对。

- 哈希桶扩容：

当哈希冲突过多时，可以动态地扩大哈希桶的数量，重新分配键值对，以减少冲突的概率。

- Java中的HashMap使用**链地址**法。

### 初始化容量为什么必须是2的n次幂？

- 当我们根据key的hash确定其在数组位置时，如果n为2的幂次方，可以保证数据的均匀插入，如果n不是2的幂次方，可能数组的一些位置永远不会插入数据，浪费数据的空间，加大hash冲突
- 当n是2的幂次方时，hash& (length - 1) == hash % length，位运算性能较好
- **总结**

为了数据的均匀分布，减少hash冲突，提高效率

### 如果输入值不是2的幂比如10会怎样？

对传入的数值减1，再进行一系列右移与运算，将第一个1之后的位数全部置为1，最后加1。变成比传入数值大的最小二进制数。

- 为什么减一

如果传入数值为二进制数，不减一会扩容为2倍，浪费空间。

### 传入map初始化为什么要+1？

减少扩容次数。

### HashMap为什么线程不安全？如何实现线程安全

hashmap不是线程安全的，hashmap在多线程会存在下面的问题：

- JDK1.7HashMap采用数组+链表的数据结构，多线程背景下，在数组扩容的时候，存在Entry链死循环和数据丢失问题。
- JDK1.8HashMap采用数组+链表+红黑二叉树的数据结构，优化了1.7中数组扩容的方案，解决了Entry链死循环和数据丢失问题。但是多线程背景下，put方法存在数据覆盖的问题。

如果要保证线程安全，可以通过这些方法来保证：

- 多线程环境可以使用Collections.synchronizedMap同步加锁的方式，还可以使用HashTable，但是同步的方式显然性能不达标，而ConurrentHashMap更适合高并发场景使用。
- ConcurrentHashmap在JDK1.7和1.8的版本改动比较大，1.7使用Segment+HashEntry分段锁的方式实现，1.8则抛弃了Segment，改为使用CAS+synchronized+Node实现，同样也加入了红黑树，避免链表过长导致性能的问题。 

主要原因是它的操作不是原⼦的，即在多个线程同时进⾏读写操作时，可能会导致数据不⼀致性或抛出异常. 1. 并发修改：当⼀个线程进⾏写操作（插⼊、删除等）时，另⼀个线程进⾏读操作，可能会导致读取到不⼀致的 数据，甚⾄抛出 ConcurrentModificationException 异常。 2. ⾮原⼦性操作： HashMap 的⼀些操作不是原⼦的，例如，检查是否存在某个键、获取某个键对应的值等，这 样在多线程环境中可能发⽣竞态条件。 为了实现线程安全的 HashMap ，有以下⼏种⽅式： 使⽤ Collections.synchronizedMap() ⽅法：可以通过 个线程安全的 HashMap ，该⽅法返回⼀个同步的 Collections.synchronizedMap() ⽅法创建⼀ Map 包装器，使得所有对 Map 的操作都是同步的。 Map synchronizedMap = Collections.synchronizedMap(new HashMap<>()); 使⽤ ConcurrentHashMap ： ConcurrentHashMap 是专⻔设计⽤于多线程环境的哈希表实现。它使⽤分段 锁机制，允许多个线程同时进⾏读操作，提⾼并发性能。 Map concurrentHashMap = new ConcurrentHashMap<>(); 使⽤锁机制：可以在⾃定义的 HashMap 操作中使⽤显式的锁（例如 ReentrantLock ）来保证线程安全

```plain
Map customMap = new HashMap<>(); 
 ReentrantLock lock = new ReentrantLock(); 
 // 在需要线程安全的操作中使⽤锁 
 lock.lock(); 
 try { 
 // 执⾏操作 
 } finally { 
    lock.unlock(); 
 }
```

### HashMap中的循环链表是如何产⽣的？ 

循环链表是由哈希冲突引起的，当多个键映射到同⼀个桶时，它们会按照插⼊的顺序形成⼀个链表。如果链表⻓度 过⻓，查找特定键的效率就会降低。为了解决这个问题， HashMap 在⼀定条件下选择将链表转换为红⿊树，提⾼查找性能。

### ConcurrentHashMap是怎么实现的？

### ConcurrentHashMap如何保证线程安全？

### HashMap的put方法流程？

### HashMap 的扩容机制

1. Java1.7扩容机制·生成新数组;·遍历老数组中的每个位置上的链表上的每个元素；·获取每个元素的key，并基于新数组长度，计算出每个元素在新数组中的下标;·将元素添加到新数组中去;·所有元素转移完之后，将新数组赋值给HashMap对象的table属性。
2. JDK1.8版本扩容。生成新数组;·遍历老数组中的每个位置上的链表或红黑树；·如果是链表，则直接将链表中的每个元素重新计算下标，并添加到新数组中去；·如果是红黑树，则先遍历红黑树，先计算出红黑树中每个元素对应在新数组中的下标位置；。统计每个下标位置的元素个数；。如果该位置下的元素个数超过了8，则生成一个新的红黑树，并将根节点添加到新数组的对应位置;·如果该位置下的元素个数没有超过8，那么则生成一个链表，并将链表的头节点添加到新数组的对应位置；·所有元素转移完了之后，将新数组赋值给HashMap对象的table属性。

### 说到HashMap,他是线程安全的吗？

### CurrentHashMap怎么保证线程安全？

### HashMap和ConcurrentHashMap的区别 ？

1. 线程安全性： HashMap 的性 HashMap 不是线程安全的。在多线程环境中，如果同时进⾏读写操作，可能会导致数据不⼀致或抛出异 常。 ConcurrentHashMap 是线程安全的，它使⽤了分段锁（Segment Locking）的机制，将整个数据结构 分成多个段（Segment），每个段都有⾃⼰的锁。这样，不同的线程可以同时访问不同的段，提⾼并发 性能。 2. 同步机制： HashMap 在实现上没有明确的同步机制，需要在外部进⾏同步，例如通过使⽤ Collections.synchronizedMap() ⽅法。 ConcurrentHashMap 内部使⽤了⼀种更细粒度的锁机制，因此在多线程环境中具有更好的性能。 3. 迭代时是否需要加锁： 在 HashMap 中，如果在迭代过程中有其他线程对其进⾏修改，可能抛出 ConcurrentModificationException 异常。 ConcurrentHashMap 允许在迭代时进⾏并发的插⼊和删除操作，⽽不会抛出异常。但是，它并不保证 迭代器的顺序，因为不同的段可能会以不同的顺序完成操作。 4. 初始化容量和负载因⼦： HashMap 可以通过构造⽅法设置初始容量和负载因⼦。 ConcurrentHashMap 在Java 8及之后版本中引⼊了 ConcurrentHashMap(int initialCapacity, float loadFactor, int concurrencyLevel) 构造⽅法，允许设置初始容量、负载因⼦和并发级 别。 5. 性能： 在低并发情况下， HashMap 的性能可能会⽐ ConcurrentHashMap 稍好，因为 需要维护额外的并发控制。 在⾼并发情况下， ConcurrentHashMap ConcurrentHashMap 的性能通常更好，因为它能够更有效地⽀持并发访问。 总的来说，如果需要在多线程环境中使⽤哈希表，⽽且需要⾼性能的并发访问，通常会选择使⽤ ConcurrentHashMap 。如果在单线程环境中使⽤，或者能够⼿动进⾏外部同步管理，那么 HashMap 可能是更简 单的选择。

### 那除了你刚刚说的CurrentHashMap还有什么方法保证HashMap线程安全？

### 那CurrentHashMap相比于synchronizedMap，通过不同的加锁方式，哪一个性能更好？

### Map和Set有什么区别？ 

Set代表⽆序的，元素不可重复的集合； Map代表具有映射关系（key-value）的集合，其所有的key是⼀个Set集合，即key⽆序且不能重复。

### List和Map有什么区别 ？

Set代表⽆序的，元素不可重复的集合； List代表有序的，元素可以重复的集合

# 源码分析

## ArrayList 源码

### 底层数据结构

线程安全：否

底层数据结构：Object[] 数组

### 成员

#### 成员变量

```java
public class ArrayList<E> extends AbstractList<E>
        implements List<E>, RandomAccess, Cloneable, java.io.Serializable {
    private static final long serialVersionUID = 8683452581122892189L;

    /**
     * 默认初始容量大小
     */
    private static final int DEFAULT_CAPACITY = 10;

    /**
     * 空数组（用于空实例）。new ArrayList(0)
     */
    private static final Object[] EMPTY_ELEMENTDATA = {};

    //用于默认大小空实例的共享空数组实例。
    //我们把它从EMPTY_ELEMENTDATA数组中区分出来，以知道在添加第一个元素时容量需要增加多少。
    private static final Object[] DEFAULTCAPACITY_EMPTY_ELEMENTDATA = {};

    /**
     * 保存ArrayList数据的数组
     */
    transient Object[] elementData; // non-private to simplify nested class access

    /**
     * ArrayList 所包含的元素个数
     */
    private int size;

}
/**
  * 作为结果性修改的版本技术，实现Java集合框架中的 Fail-Fast 机制。
  * 但无法保证原子性，所以无法保证线程安全
  */
protected transient int modCount = 0;
```

#### 构造方法

```java
/**
 * 默认初始容量大小
 */
private static final int DEFAULT_CAPACITY = 10;

private static final Object[] DEFAULTCAPACITY_EMPTY_ELEMENTDATA = {};

/**
 * 默认构造函数，使用初始容量10构造一个空列表(无参数构造)
 */
public ArrayList() {
    this.elementData = DEFAULTCAPACITY_EMPTY_ELEMENTDATA;
}

/**
 * 带初始容量参数的构造函数。（用户自己指定容量）
 */
public ArrayList(int initialCapacity) {
    if (initialCapacity > 0) {//初始容量大于0
        //创建initialCapacity大小的数组
        this.elementData = new Object[initialCapacity];
    } else if (initialCapacity == 0) {//初始容量等于0
        //创建空数组
        this.elementData = EMPTY_ELEMENTDATA;
    } else {//初始容量小于0，抛出异常
        throw new IllegalArgumentException("Illegal Capacity: " + initialCapacity);
    }
}


/**
 *构造包含指定collection元素的列表，这些元素利用该集合的迭代器按顺序返回
 *如果指定的集合为null，throws NullPointerException。
 */
public ArrayList(Collection<? extends E> c) {
    elementData = c.toArray();
    if ((size = elementData.length) != 0) {
        if (elementData.getClass() != Object[].class)
            // 数组长度部位0且不是Object类型数据
            elementData = Arrays.copyOf(elementData, size, Object[].class);
    } else {
        // replace with empty array.
        this.elementData = EMPTY_ELEMENTDATA;
    }
}
```

#### 扩容机制

add 方法 调用 ensureCapacityInternal(size + 1); 确保最小容量足够容纳多一个元素。内部调用 ensureExplicitCapacity() 判断当前最小容量是否需要扩容。 当最小容量 > 当前数组长度时，扩容。

最小容量计算 calculateCapacity(Object[] elementData, int minCapacity) 此时 elementData 为成员变量，minCapacity 为 size + 1。为空数组返回 10 与 minCapcacity 的较大值，不会空则返回 minCapacity。

##### add 方法

```java
/**
  * 将指定的元素追加到此列表的末尾。
  */
public boolean add(E e) {
    // 加元素之前，先调用ensureCapacityInternal方法
    ensureCapacityInternal(size + 1);  // Increments modCount!!
    // 这里看到ArrayList添加元素的实质就相当于为数组赋值
    elementData[size++] = e;
    return true;
}
```

##### ensureCapacityInternal 方法

```java
// 根据给定的最小容量和当前数组元素来计算所需容量。
private static int calculateCapacity(Object[] elementData, int minCapacity) {
    // 如果当前数组元素为空数组（初始情况），返回默认容量和最小容量中的较大值作为所需容量
    if (elementData == DEFAULTCAPACITY_EMPTY_ELEMENTDATA) {
        return Math.max(DEFAULT_CAPACITY, minCapacity);
    }
    // 否则直接返回最小容量
    return minCapacity;
}

// 确保内部容量达到指定的最小容量。
private void ensureCapacityInternal(int minCapacity) {
    ensureExplicitCapacity(calculateCapacity(elementData, minCapacity));
}
```

##### ensureExplicitCapacity 方法

```java
//判断是否需要扩容
private void ensureExplicitCapacity(int minCapacity) {
    modCount++;
    //判断当前数组容量是否足以存储minCapacity个元素
    if (minCapacity - elementData.length > 0)
        //调用grow方法进行扩容
        grow(minCapacity);
}
```

##### grow 方法

新容量默认为旧容量 1.5 倍，但是有特殊判断。最后就旧数组值拷贝到新数组上，返回新数组。

```java
/**
 * 要分配的最大数组大小
 */
private static final int MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;

/**
 * ArrayList扩容的核心方法。
 */
private void grow(int minCapacity) {
    // oldCapacity为旧容量，newCapacity为新容量
    int oldCapacity = elementData.length;
    // 将oldCapacity 右移一位，其效果相当于oldCapacity /2，
    // 我们知道位运算的速度远远快于整除运算，整句运算式的结果就是将新容量更新为旧容量的1.5倍，
    int newCapacity = oldCapacity + (oldCapacity >> 1);

    // 然后检查新容量是否大于最小需要容量，若还是小于最小需要容量，那么就把最小需要容量当作数组的新容量，
    if (newCapacity - minCapacity < 0)
        newCapacity = minCapacity;

    // 如果新容量大于 MAX_ARRAY_SIZE,进入(执行) `hugeCapacity()` 方法来比较 minCapacity 和 MAX_ARRAY_SIZE，
    // 如果minCapacity大于最大容量，则新容量则为`Integer.MAX_VALUE`，否则，新容量大小则为 MAX_ARRAY_SIZE 即为 `Integer.MAX_VALUE - 8`。
    if (newCapacity - MAX_ARRAY_SIZE > 0)
        newCapacity = hugeCapacity(minCapacity);

    // minCapacity is usually close to size, so this is a win:
    elementData = Arrays.copyOf(elementData, newCapacity);
}

private static int hugeCapacity(int minCapacity) {
    if (minCapacity < 0) // overflow
        throw new OutOfMemoryError();
    // 对minCapacity和MAX_ARRAY_SIZE进行比较
    // 若minCapacity大，将Integer.MAX_VALUE作为新数组的大小
    // 若MAX_ARRAY_SIZE大，将MAX_ARRAY_SIZE作为新数组的大小
    // MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;
    return (minCapacity > MAX_ARRAY_SIZE) ?
        Integer.MAX_VALUE :
        MAX_ARRAY_SIZE;
}
```

##### Array.copyOf 方法

```java
public static int[] copyOf(int[] original, int newLength) {
    // 申请一个新的数组
    int[] copy = new int[newLength];
    // 调用System.arraycopy,将源数组中的数据进行拷贝,并返回新的数组
    System.arraycopy(original, 0, copy, 0,
        Math.min(original.length, newLength));
    return copy;
}

// 我们发现 arraycopy 是一个 native 方法,接下来我们解释一下各个参数的具体意义
/**
*   复制数组
* @param src 源数组
* @param srcPos 源数组中的起始位置
* @param dest 目标数组
* @param destPos 目标数组中的起始位置
* @param length 要复制的数组元素的数量
*/
public static native void arraycopy(Object src,  int  srcPos,
                                    Object dest, int destPos,
                                    int length);
```

## LinkedList 源码分析

## HashMap 源码分析

### 底层数据结构

#### JDK1.8 之前

链表 + 数组

发生哈希冲突时，使用拉链法（头插法）

```plain
static int hash(int h) {
    // This function ensures that hashCodes that differ only by
    // constant multiples at each bit position have a bounded
    // number of collisions (approximately 8 at default load factor).

    h ^= (h >>> 20) ^ (h >>> 12);
    return h ^ (h >>> 7) ^ (h >>> 4);
}
```

#### JDK1.8 之后

链表 + 数组 + 红黑树

当链表长度 > 8 且 数组长度 > 64 时，调用 treeifyBin() 将链表转化为红黑树。否则则是调用 resize() 对数组扩容。（尾插法）

```plain
    static final int hash(Object key) {
      int h;
      // key.hashCode()：返回散列值也就是hashcode
      // ^：按位异或
      // >>>:无符号右移，忽略符号位，空位都以0补齐
      return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
  }
```

### 成员

#### 成员变量

```plain
public class HashMap<K,V> extends AbstractMap<K,V> implements Map<K,V>, Cloneable, Serializable {
    // 序列号
    private static final long serialVersionUID = 362498820763181265L;
    // 默认的初始容量是16
    static final int DEFAULT_INITIAL_CAPACITY = 1 << 4;
    // 最大容量
    static final int MAXIMUM_CAPACITY = 1 << 30;
    // 默认的负载因子
    static final float DEFAULT_LOAD_FACTOR = 0.75f;
    // 当桶(bucket)上的结点数大于等于这个值时会转成红黑树
    static final int TREEIFY_THRESHOLD = 8;
    // 当桶(bucket)上的结点数小于等于这个值时树转链表
    static final int UNTREEIFY_THRESHOLD = 6;
    // 桶中结构转化为红黑树对应的table的最小容量
    static final int MIN_TREEIFY_CAPACITY = 64;
    //* 存储元素的数组，总是2的幂次倍
    transient Node<k,v>[] table;
    // 一个包含了映射中所有键值对的集合视图
    transient Set<map.entry<k,v>> entrySet;
    //* 存放元素的个数，注意这个不等于数组的长度。
    transient int size;
    // 每次扩容和更改map结构的计数器
    transient int modCount;
    // 阈值(容量*负载因子) 当实际大小超过阈值时，会进行扩容
    int threshold;
    //* 负载因子
    final float loadFactor;
}
```

##### Node 节点类源码

```plain
// 继承自 Map.Entry<K,V>
static class Node<K,V> implements Map.Entry<K,V> {
       final int hash;// 哈希值，存放元素到hashmap中时用来与其他元素hash值比较
       final K key;//键
       V value;//值
       // 指向下一个节点
       Node<K,V> next;
       Node(int hash, K key, V value, Node<K,V> next) {
            this.hash = hash;
            this.key = key;
            this.value = value;
            this.next = next;
        }
        public final K getKey()        { return key; }
        public final V getValue()      { return value; }
        public final String toString() { return key + "=" + value; }
        // 重写hashCode()方法
        public final int hashCode() {
            return Objects.hashCode(key) ^ Objects.hashCode(value);
        }

        public final V setValue(V newValue) {
            V oldValue = value;
            value = newValue;
            return oldValue;
        }
        // 重写 equals() 方法
        public final boolean equals(Object o) {
            if (o == this)
                return true;
            if (o instanceof Map.Entry) {
                Map.Entry<?,?> e = (Map.Entry<?,?>)o;
                if (Objects.equals(key, e.getKey()) &&
                    Objects.equals(value, e.getValue()))
                    return true;
            }
            return false;
        }
}
```

##### 树节点类源码

```plain
static final class TreeNode<K,V> extends LinkedHashMap.Entry<K,V> {
        TreeNode<K,V> parent;  // 父
        TreeNode<K,V> left;    // 左
        TreeNode<K,V> right;   // 右
        TreeNode<K,V> prev;    // needed to unlink next upon deletion
        boolean red;           // 判断颜色
        TreeNode(int hash, K key, V val, Node<K,V> next) {
            super(hash, key, val, next);
        }
        // 返回根节点
        final TreeNode<K,V> root() {
            for (TreeNode<K,V> r = this, p;;) {
                if ((p = r.parent) == null)
                    return r;
                r = p;
       }
```

#### 构造方法

##### 构造一个空的 `HashMap` ，默认初始容量（16）和默认负载因子（0.75）。

```java
public HashMap() {
    this.loadFactor = DEFAULT_LOAD_FACTOR; // 将默认的加载因子0.75赋值给loadFactor，并没有创建数组
}
```

##### 构造一个具有指定的初始容量和默认负载因子（0.75） `HashMap`。 

```java
// 指定“容量大小”的构造函数
public HashMap(int initialCapacity) {
    this(initialCapacity, DEFAULT_LOAD_FACTOR);
}
```

##### 构造一个具有指定的初始容量和负载因子的 `HashMap`。

```java
/*
	 指定“容量大小”和“加载因子”的构造函数
	 initialCapacity: 指定的容量
	 loadFactor:指定的加载因子
*/
public HashMap(int initialCapacity, float loadFactor) {
    //判断初始化容量initialCapacity是否小于0
    if (initialCapacity < 0)
        //如果小于0，则抛出非法的参数异常IllegalArgumentException
        throw new IllegalArgumentException("Illegal initial capacity: " +
                                           initialCapacity);
    //判断初始化容量initialCapacity是否大于集合的最大容量MAXIMUM_CAPACITY-》2的30次幂
    if (initialCapacity > MAXIMUM_CAPACITY)
        //如果超过MAXIMUM_CAPACITY，会将MAXIMUM_CAPACITY赋值给initialCapacity
        initialCapacity = MAXIMUM_CAPACITY;
    //判断负载因子loadFactor是否小于等于0或者是否是一个非数值
    if (loadFactor <= 0 || Float.isNaN(loadFactor))
        //如果满足上述其中之一，则抛出非法的参数异常IllegalArgumentException
        throw new IllegalArgumentException("Illegal load factor: " +
                                           loadFactor);
    //将指定的加载因子赋值给HashMap成员变量的负载因子loadFactor
    this.loadFactor = loadFactor;
        /*
    		tableSizeFor(initialCapacity) 
            判断指定的初始化容量是否是2的n次幂，如果不是那么会变为比指定初始化容量大的最小的2的n次幂。
    		但是注意，在tableSizeFor方法体内部将计算后的数据返回给调用这里了，并且直接赋值给threshold边界值了。
            此时构造函数中设置的 threshold 为暂存值，只是"希望数组容量达到多少"
            真正的threshold在首次put()里，resize()方法中重新计算
            构造函数中的 threshold 只是用来指导初始化数组时的长度选择，它最终会被 put()中的 resize 覆盖掉。
    	*/
    this.threshold = tableSizeFor(initialCapacity);
}
最后调用了tableSizeFor，来看一下方法实现：
   /**
     * Returns a power of two size for the given target capacity.
       返回比指定初始化容量大的最小的2的n次幂
     */
static final int tableSizeFor(int cap) {
    int n = cap - 1;
    // >>> 为无符号右移 高位补0
    n |= n >>> 1; 
    n |= n >>> 2;
    n |= n >>> 4;
    n |= n >>> 8;
    n |= n >>> 16;
    /** 
      * int 为32位有符号整数，1 + 2 + 4 + 8 + 16 = 31
      * 上诉实现将最高位1往下扩散31次，覆盖所有低位
      */
    return (n < 0) ? 1 : (n >= MAXIMUM_CAPACITY) ? MAXIMUM_CAPACITY : n + 1;
}
```

##### 包含另一个“Map”的构造函数

```java
//构造一个映射关系与指定 Map 相同的新 HashMap。
public HashMap(Map<? extends K, ? extends V> m) {
    //负载因子loadFactor变为默认的负载因子0.75
    this.loadFactor = DEFAULT_LOAD_FACTOR;
    putMapEntries(m, false);
}
```

##### 关于 putMapEntries

```java
final void putMapEntries(Map<? extends K, ? extends V> m, boolean evict) {
    //获取参数集合的长度
    int s = m.size();
    if (s > 0)
    {
        //判断参数集合的长度是否大于0，说明大于0
        if (table == null)  // 判断table是否已经初始化
        { // pre-size
            // 未初始化，s为m的实际元素个数
            float ft = ((float)s / loadFactor) + 1.0F;
            int t = ((ft < (float)MAXIMUM_CAPACITY) ?
                     (int)ft : MAXIMUM_CAPACITY);
            // 计算得到的t大于阈值，则初始化阈值
            if (t > threshold)
                threshold = tableSizeFor(t);
        }
            // 已初始化，并且m元素个数大于阈值，进行扩容处理
        else if (s > threshold)
            resize();
        // 将m中的所有元素添加至HashMap中
        for (Map.Entry<? extends K, ? extends V> e : m.entrySet()) {
            K key = e.getKey();
            V value = e.getValue();
            putVal(hash(key), key, value, false, evict);
        }
    }
}
```

#### 成员方法

##### put 方法

 先根据 key 算出位置，如果位置没人就直接放；如果有人，就判断是覆盖、链表追加，还是红黑树插入。 

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1747123820676-2620d744-cd86-4a49-8f66-82a2dbac5061.png)

```java
public V put(K key, V value) 
{
        return putVal(hash(key), key, value, false, true);
}
final V putVal(int hash, K key, V value, boolean onlyIfAbsent,
                   boolean evict) {
    Node<K,V>[] tab; Node<K,V> p; int n, i;
    /*
    	1）transient Node<K,V>[] table; 表示存储Map集合中元素的数组。
    	2）(tab = table) == null 表示将空的table赋值给tab,然后判断tab是否等于null，第一次肯定是null
    	3）(n = tab.length) == 0 表示将数组的长度0赋值给n,然后判断n是否等于0，n等于0
    	由于if判断使用双或，满足一个即可，则执行代码 n = (tab = resize()).length; 进行数组初始化。
    	并将初始化好的数组长度赋值给n.
    	4）执行完n = (tab = resize()).length，数组tab每个空间都是null
    */
    if ((tab = table) == null || (n = tab.length) == 0)
        n = (tab = resize()).length;
    /*
    	1）i = (n - 1) & hash 表示计算数组的索引赋值给i，即确定元素存放在哪个桶中
    	2）p = tab[i = (n - 1) & hash]表示获取计算出的位置的数据赋值给节点p
    	3) (p = tab[i = (n - 1) & hash]) == null 判断节点位置是否等于null，
           如果为null，则执行代码：tab[i] = newNode(hash, key, value, null);
           根据键值对创建新的节点放入该位置的桶中
        小结：如果当前桶没有哈希碰撞冲突，则直接把键值对插入空间位置
    */ 
    if ((p = tab[i = (n - 1) & hash]) == null)
        //创建一个新的节点存入到桶中
        tab[i] = newNode(hash, key, value, null);
    else {
         // 执行else说明tab[i]不等于null，表示这个位置已经有值了。
        Node<K,V> e; K k;
        /*
        	比较桶中第一个元素(数组中的结点)的hash值和key是否相等
        	1）p.hash == hash ：p.hash表示原来存在数据的hash值  hash表示后添加数据的hash值 比较两个hash值是否相等
                 说明：p表示tab[i]，即 newNode(hash, key, value, null)方法返回的Node对象。
                    Node<K,V> newNode(int hash, K key, V value, Node<K,V> next) 
                    {
                        return new Node<>(hash, key, value, next);
                    }
                    而在Node类中具有成员变量hash用来记录着之前数据的hash值的
             2）(k = p.key) == key ：p.key获取原来数据的key赋值给k  key 表示后添加数据的key 比较两个key的地址值是否相等
             3）key != null && key.equals(k)：能够执行到这里说明两个key的地址值不相等，
             那么先判断后添加的key是否等于null，
             如果不等于null再调用equals方法判断两个key的内容是否相等
        */
        if (p.hash == hash &&
            ((k = p.key) == key || (key != null && key.equals(k))))
                /*
                	说明：两个元素哈希值相等，并且key的值也相等
                	将旧的元素整体对象赋值给e，用e来记录
                */ 
                e = p;
        // hash值不相等或者key不相等；判断p是否为红黑树结点
        else if (p instanceof TreeNode)
            // 放入树中
            e = ((TreeNode<K,V>)p).putTreeVal(this, tab, hash, key, value);
        // 说明是链表节点
        else {
            /*
            	1)如果是链表的话需要遍历到最后节点然后插入
            	2)采用循环遍历的方式，判断链表中是否有重复的key
            */
            for (int binCount = 0; ; ++binCount) {
                /*
                	1)e = p.next 获取p的下一个元素赋值给e
                	2)(e = p.next) == null 判断p.next是否等于null，等于null，说明p没有下一个元					素，那么此时到达了链表的尾部，还没有找到重复的key,则说明HashMap没有包含该键
                	将该键值对插入链表中
                */
                if ((e = p.next) == null) {
                    /*
                    	1）创建一个新的节点插入到尾部
                    	 p.next = newNode(hash, key, value, null);
                    	 Node<K,V> newNode(int hash, K key, V value, Node<K,V> next) 
                    	 {
                                return new Node<>(hash, key, value, next);
                         }
                         注意第四个参数next是null，因为当前元素插入到链表末尾了，那么下一个节点肯定是								null
                         2）这种添加方式也满足链表数据结构的特点，每次向后添加新的元素
                    */
                    p.next = newNode(hash, key, value, null);
                    /*
                    	1)节点添加完成之后判断此时节点个数是否大于TREEIFY_THRESHOLD临界值8，如果大于
                    	则将链表转换为红黑树
                    	2）int binCount = 0 ：表示for循环的初始化值。从0开始计数。记录着遍历节点的个						数。值是0表示第一个节点，1表示第二个节点。。。。7表示第八个节点，加上数组中的的一						个元素，元素个数是9
                    	TREEIFY_THRESHOLD - 1 --》8 - 1 ---》7
                    	如果binCount的值是7(加上数组中的的一个元素，元素个数是9)
                    	TREEIFY_THRESHOLD - 1也是7，此时转换红黑树
                    */
                    if (binCount >= TREEIFY_THRESHOLD - 1) // -1 for 1st
                        //转换为红黑树
                        treeifyBin(tab, hash);
                    // 跳出循环
                    break;
                }
                 
                /*
                	执行到这里说明e = p.next 不是null，不是最后一个元素。继续判断链表中结点的key值与插入的元素的key值是否相等
                */
                if (e.hash == hash &&
                    ((k = e.key) == key || (key != null && key.equals(k))))
                    // 相等，跳出循环
                    /*
                		要添加的元素和链表中的存在的元素的key相等了，则跳出for循环。不用再继续比较了
                		直接执行下面的if语句去替换去 if (e != null) 
                	*/
                    break;
                /*
                	说明新添加的元素和当前节点不相等，继续查找下一个节点。
                	用于遍历桶中的链表，与前面的e = p.next组合，可以遍历链表
                */
                p = e;
            }
        }
        /*
        	表示在桶中找到key值、hash值与插入元素相等的结点
        	也就是说通过上面的操作找到了重复的键，所以这里就是把该键的值变为新的值，并返回旧值
        	这里完成了put方法的修改功能
        */
        if (e != null) { 
            // 记录e的value
            V oldValue = e.value;
            // onlyIfAbsent为false或者旧值为null
            if (!onlyIfAbsent || oldValue == null)
                //用新值替换旧值
                //e.value 表示旧值  value表示新值 
                e.value = value;
            // 访问后回调
            afterNodeAccess(e);
            // 返回旧值
            return oldValue;
        }
    }
    //修改记录次数
    ++modCount;
    // 判断实际大小是否大于threshold阈值，如果超过则扩容
    if (++size > threshold)
        resize();
    // 插入后回调
    afterNodeInsertion(evict);
    return null;
} 
public V put(K key, V value)
    if (table == EMPTY_TABLE) {
        inflateTable(threshold);
    }
    if (key == null)
        return putForNullKey(value);
    int hash = hash(key);
    int i = indexFor(hash, table.length);
    for (Entry<K,V> e = table[i]; e != null; e = e.next) { // 先遍历
        Object k;
        if (e.hash == hash && ((k = e.key) == key || key.equals(k))) {
            V oldValue = e.value;
            e.value = value;
            e.recordAccess(this);
            return oldValue;
        }
    }

    modCount++;
    addEntry(hash, key, value, i);  // 再插入
    return null;
}
```

##### treeifyBin 方法

```java
/**
   * Replaces all linked nodes in bin at index for given hash unless
   * table is too small, in which case resizes instead.
     替换指定哈希表的索引处桶中的所有链接节点，除非表太小，否则将修改大小。
     Node<K,V>[] tab = tab 数组名
     int hash = hash表示哈希值
  */
final void treeifyBin(Node<K,V>[] tab, int hash) {
    int n, index; Node<K,V> e;
    /*
        	如果当前数组为空或者数组的长度小于进行树形化的阈值(MIN_TREEIFY_CAPACITY = 64),
        	就去扩容。而不是将节点变为红黑树。
        	目的：如果数组很小，那么转换红黑树，然后遍历效率要低一些。这时进行扩容，那么重新计算哈希值
        	，链表长度有可能就变短了，数据会放到数组中，这样相对来说效率高一些。
        */
    if (tab == null || (n = tab.length) < MIN_TREEIFY_CAPACITY)
        //扩容方法
        resize();
    else if ((e = tab[index = (n - 1) & hash]) != null) {
        /*
            	1）执行到这里说明哈希表中的数组长度大于阈值64，开始进行树形化
            	2）e = tab[index = (n - 1) & hash]表示将数组中的元素取出赋值给e,e是哈希表中指定位					置桶里的链表节点，从第一个开始
            */
        //hd：红黑树的头结点   tl :红黑树的尾结点
        TreeNode<K,V> hd = null, tl = null;
        do {
            //新创建一个树的节点，内容和当前链表节点e一致
            TreeNode<K,V> p = replacementTreeNode(e, null);
            if (tl == null)
                //将新创键的p节点赋值给红黑树的头结点
                hd = p;
            else {
                /*
                    	 p.prev = tl：将上一个节点p赋值给现在的p的前一个节点
                    	 tl.next = p;将现在节点p作为树的尾结点的下一个节点
                    */
                p.prev = tl;
                tl.next = p;
            }
            tl = p;
            /*
                	e = e.next 将当前节点的下一个节点赋值给e,如果下一个节点不等于null
                	则回到上面继续取出链表中节点转换为红黑树
                */
        } while ((e = e.next) != null);
        /*
            	让桶中的第一个元素即数组中的元素指向新建的红黑树的节点，以后这个桶里的元素就是红黑树
            	而不是链表数据结构了
            */
        if ((tab[index] = hd) != null)
            hd.treeify(tab);
    }
}
```

##### get 方法

```java
public V get(Object key) {
    Node<K,V> e;
    return (e = getNode(hash(key), key)) == null ? null : e.value;
}

final Node<K,V> getNode(int hash, Object key) {
    Node<K,V>[] tab; Node<K,V> first, e; int n; K k;
    //如果哈希表不为空并且key对应的桶上不为空
    if ((tab = table) != null && (n = tab.length) > 0 &&
        (first = tab[(n - 1) & hash]) != null) {
        /* 
        	判断数组元素是否相等
        	根据索引的位置检查第一个元素
        	注意：总是检查第一个元素
        */
        if (first.hash == hash && // always check first node
            ((k = first.key) == key || (key != null && key.equals(k))))
            return first;
        // 如果不是第一个元素，判断是否有后续节点
        if ((e = first.next) != null) {
            // 判断是否是红黑树，是的话调用红黑树中的getTreeNode方法获取节点
            if (first instanceof TreeNode)
                return ((TreeNode<K,V>)first).getTreeNode(hash, key);
            do {
                // 不是红黑树的话，那就是链表结构了，通过循环的方法判断链表中是否存在该key
                if (e.hash == hash &&
                    ((k = e.key) == key || (key != null && key.equals(k))))
                    return e;
            } while ((e = e.next) != null);
        }
    }
    return null;
}
```

##### resize 方法

```java
final Node<K,V>[] resize() {
    //得到当前数组
    Node<K,V>[] oldTab = table;
    //如果当前数组等于null长度返回0，否则返回当前数组的长度
    int oldCap = (oldTab == null) ? 0 : oldTab.length;
    //当前阀值点 默认是12(16*0.75)
    int oldThr = threshold;
    int newCap, newThr = 0;
    //如果老的数组长度大于0
    //开始计算扩容后的大小
    if (oldCap > 0) {
        // 超过最大值就不再扩充了，就只好随你碰撞去吧
        if (oldCap >= MAXIMUM_CAPACITY) {
            //修改阈值为int的最大值
            threshold = Integer.MAX_VALUE;
            return oldTab;
        }
        /*
        	没超过最大值，就扩充为原来的2倍
        	1)(newCap = oldCap << 1) < MAXIMUM_CAPACITY 扩大到2倍之后容量要小于最大容量
        	2）oldCap >= DEFAULT_INITIAL_CAPACITY 原数组长度大于等于数组初始化长度16
        */
        else if ((newCap = oldCap << 1) < MAXIMUM_CAPACITY &&
                 oldCap >= DEFAULT_INITIAL_CAPACITY)
            //阈值扩大一倍
            newThr = oldThr << 1; // double threshold
    }
    //老阈值点大于0 直接赋值
    else if (oldThr > 0) // 老阈值赋值给新的数组长度
        newCap = oldThr;
    else {// 直接使用默认值
        newCap = DEFAULT_INITIAL_CAPACITY;//16
        newThr = (int)(DEFAULT_LOAD_FACTOR * DEFAULT_INITIAL_CAPACITY);
    }
    // 计算新的resize最大上限
    if (newThr == 0) {
        float ft = (float)newCap * loadFactor;
        newThr = (newCap < MAXIMUM_CAPACITY && ft < (float)MAXIMUM_CAPACITY ?
                  (int)ft : Integer.MAX_VALUE);
    }
    //新的阀值 默认原来是12 乘以2之后变为24
    threshold = newThr;
    //创建新的哈希表
    @SuppressWarnings({"rawtypes","unchecked"})
    //newCap是新的数组长度--》32
    Node<K,V>[] newTab = (Node<K,V>[])new Node[newCap];
    table = newTab;
    //判断旧数组是否等于空
    if (oldTab != null) {
        // 把每个bucket都移动到新的buckets中
        //遍历旧的哈希表的每个桶，重新计算桶里元素的新位置
        for (int j = 0; j < oldCap; ++j) {
            Node<K,V> e;
            if ((e = oldTab[j]) != null) {
                //原来的数据赋值为null 便于GC回收
                oldTab[j] = null;
                //判断数组是否有下一个引用
                if (e.next == null)
                    //没有下一个引用，说明不是链表，当前桶上只有一个键值对，直接插入
                    newTab[e.hash & (newCap - 1)] = e;
                //判断是否是红黑树
                else if (e instanceof TreeNode)
                    //说明是红黑树来处理冲突的，则调用相关方法把树分开
                    ((TreeNode<K,V>)e).split(this, newTab, j, oldCap);
                else { // 采用链表处理冲突
                    Node<K,V> loHead = null, loTail = null;
                    Node<K,V> hiHead = null, hiTail = null;
                    Node<K,V> next;
                    //通过上述讲解的原理来计算节点的新位置
                    do {
                        // 原索引
                        next = e.next;
                     	//这里来判断如果等于true e这个节点在resize之后不需要移动位置
                        if ((e.hash & oldCap) == 0) {
                            if (loTail == null)
                                loHead = e;
                            else
                                loTail.next = e;
                            loTail = e;
                        }
                        // 原索引+oldCap
                        else {
                            if (hiTail == null)
                                hiHead = e;
                            else
                                hiTail.next = e;
                            hiTail = e;
                        }
                    } while ((e = next) != null);
                    // 原索引放到bucket里
                    if (loTail != null) {
                        loTail.next = null;
                        newTab[j] = loHead;
                    }
                    // 原索引+oldCap放到bucket里
                    if (hiTail != null) {
                        hiTail.next = null;
                        newTab[j + oldCap] = hiHead;
                    }
                }
            }
        }
    }
    return newTab;
}
```

##### remove()

```java
//remove方法的具体实现在removeNode方法中，所以我们重点看下removeNode方法
public V remove(Object key) {
        Node<K,V> e;
        return (e = removeNode(hash(key), key, null, false, true)) == null ?
            null : e.value;
}

final Node<K,V> removeNode(int hash, Object key, Object value,
                               boolean matchValue, boolean movable) {
        Node<K,V>[] tab; Node<K,V> p; int n, index;
    	//根据hash找到位置 
    	//如果当前key映射到的桶不为空
        if ((tab = table) != null && (n = tab.length) > 0 &&
            (p = tab[index = (n - 1) & hash]) != null) {
            Node<K,V> node = null, e; K k; V v;
            //如果桶上的节点就是要找的key，则将node指向该节点
            if (p.hash == hash &&
                ((k = p.key) == key || (key != null && key.equals(k))))
                node = p;
            else if ((e = p.next) != null) {
                //说明节点存在下一个节点
                if (p instanceof TreeNode)
                    //说明是以红黑树来处理的冲突，则获取红黑树要删除的节点
                    node = ((TreeNode<K,V>)p).getTreeNode(hash, key);
                else {
                    //判断是否以链表方式处理hash冲突，是的话则通过遍历链表来寻找要删除的节点
                    do {
                        if (e.hash == hash &&
                            ((k = e.key) == key ||
                             (key != null && key.equals(k)))) {
                            node = e;
                            break;
                        }
                        p = e;
                    } while ((e = e.next) != null);
                }
            }
            //比较找到的key的value和要删除的是否匹配
            if (node != null && (!matchValue || (v = node.value) == value ||
                                 (value != null && value.equals(v)))) {
                //通过调用红黑树的方法来删除节点
                if (node instanceof TreeNode)
                    ((TreeNode<K,V>)node).removeTreeNode(this, tab, movable);
                else if (node == p)
                    //链表删除
                    tab[index] = node.next;
                else
                    p.next = node.next;
                //记录修改次数
                ++modCount;
                //变动的数量
                --size;
                afterNodeRemoval(node);
                return node;
            }
        }
        return null;
}
```



## ConcurrentHashMap 源码分析

# 为什么需要？

 	

- jdk1.7 HashMap在多线程下 put 可能出现死循环

HashMap在扩容时，使用头插法，由于 HashMap 在遍历旧链表时，是从头开始的。导致新链表顺序与旧链表形成反转。具体为线程1扩容刚开始只记到A的下一个节点为B，其他没有执行，然后线程2执行完整个扩容，然后线程1恢复后当他重新开始扩容时，到b节点时，b的next被线程2修改为A，导致成环。

 	

- Hashtable的低效

给几乎所有公开的（public）方法都加上 synchronized 关键字。锁的粒度太大导致，只有一把对象锁。

# 数据结构

## 1.7

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764122385859-3cc0f6ab-6663-4d25-a355-7ba159f3c1f3.png)

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764122379692-cb89c06a-f6c1-4429-9359-ee974e94ac0b.gif)编辑

默认由16个 segment 组成，每个 `segement` 可以看成一个 HashMap。

通过锁住一个segment，保证无并发冲突，锁粒度大。最大并发度为segment个数，不代表只支持16个线程的并发。

最大并发度指最多有多少个线程无冲突运行，不是最大支持多少个线程运行。

## 1.8

![img](https://cdn.nlark.com/yuque/0/2025/png/53862437/1764122385881-1462dffa-87dd-40b9-b8d4-0b370fbda004.png)

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764122379792-8de6bc21-c9fa-426f-8047-8150d15ab67c.gif)编辑

**在 Java 8 中，****ConcurrentHashMap** **和** **HashMap** **在宏观的数据结构上是一致的，都采用了‘数组 + 链表 / 红黑树’的模型。但为了实现高并发下的线程安全，****ConcurrentHashMap** **在其实现的每一个细节上都与** **HashMap** **截然不同：它通过** **volatile** **保证内存可见性，通过 CAS 操作实现乐观的无锁更新，通过** **synchronized** **锁住桶的头节点来实现细粒度的并发控制，并且拥有一个安全、高效的并发扩容机制。可以说，****ConcurrentHashMap** **是在** **HashMap** **的数据结构基础上，进行了一次彻底的、为并发而生的‘重装升级’。”**

### 存储结构

```plain
transient volatile Node<K,V>[] table;
 private transient volatile int sizeCtl;
private final Node<K,V>[] initTable() {
    Node<K,V>[] tab; int sc;
    while ((tab = table) == null || tab.length == 0) {
        // 通过自旋保证table数字被成功初始化
        if ((sc = sizeCtl) < 0)
            Thread.yield(); // 主动让出cpu时间片，进入就绪队列
        else if (U.compareAndSwapInt(this, SIZECTL, sc, -1)) {
            // cas原子操作，将值修改为-1
            try {
                if ((tab = table) == null || tab.length == 0) {
                    // 双重检查
                    int n = (sc > 0) ? sc : DEFAULT_CAPACITY;
                    @SuppressWarnings("unchecked")
                    Node<K,V>[] nt = (Node<K,V>[])new Node<?,?>[n];
                    table = tab = nt;
                    sc = n - (n >>> 2);
                }
            } finally {
                sizeCtl = sc;
            }
            break;
        }
    }
    return tab;
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764122379816-434b5091-9a39-4a39-8110-055781143e01.gif)

**在多线程环境下，安全、高效地创建并初始化** **ConcurrentHashMap** **内部的** **table** **数组，并确保这个初始化动作只发生一次。**

 	

- **sizeCtl** **变量**：这是 ConcurrentHashMap 中一个极其重要的控制变量。它的值有不同的含义：

 	

-  	 		

- **> 0**: 在**初始化前**，表示 table 的初始容量。或者，在**初始化后**，表示扩容的阈值。

-  		

- **= 0**: 默认值，表示 table 还没初始化，将使用默认容量。

-  		

- **= -1**: **这是一个“锁”状态！** 表示**正有某个线程正在进行初始化或扩容**。

-  		

- **< -1**: 表示有多个线程正在进行扩容。

-  	 	

```plain
public V put(K key, V value) {
    return putVal(key, value, false);
}

/** Implementation for put and putIfAbsent */
final V putVal(K key, V value, boolean onlyIfAbsent) {
    // key 和 value 不能为空
    if (key == null || value == null) throw new NullPointerException();
    int hash = spread(key.hashCode());
    int binCount = 0;
    for (Node<K,V>[] tab = table;;) {
        // f = 目标位置元素
        Node<K,V> f; int n, i, fh;// fh 后面存放目标位置的元素 hash 值
        if (tab == null || (n = tab.length) == 0)
            // 数组桶为空，初始化数组桶（自旋+CAS)
            tab = initTable();
        else if ((f = tabAt(tab, i = (n - 1) & hash)) == null) {
            // 桶内为空，CAS 放入，不加锁，成功了就直接 break 跳出
            if (casTabAt(tab, i, null,new Node<K,V>(hash, key, value, null)))
                break;  // no lock when adding to empty bin
        }
        else if ((fh = f.hash) == MOVED)
            // 扩容情况
            tab = helpTransfer(tab, f);
        else {
            // put竞争
            V oldVal = null;
            // 使用 synchronized 加锁加入节点
            synchronized (f) {
                if (tabAt(tab, i) == f) {
                    // 说明是链表
                    if (fh >= 0) {
                        binCount = 1;
                        // 循环加入新的或者覆盖节点
                        for (Node<K,V> e = f;; ++binCount) {
                            K ek;
                            if (e.hash == hash &&
                                ((ek = e.key) == key ||
                                 (ek != null && key.equals(ek)))) {
                                oldVal = e.val;
                                if (!onlyIfAbsent)
                                    e.val = value;
                                break;
                            }
                            Node<K,V> pred = e;
                            if ((e = e.next) == null) {
                                pred.next = new Node<K,V>(hash, key,
                                                          value, null);
                                break;
                            }
                        }
                    }
                    else if (f instanceof TreeBin) {
                        // 红黑树
                        Node<K,V> p;
                        binCount = 2;
                        if ((p = ((TreeBin<K,V>)f).putTreeVal(hash, key,
                                                       value)) != null) {
                            oldVal = p.val;
                            if (!onlyIfAbsent)
                                p.val = value;
                        }
                    }
                }
            }
            if (binCount != 0) {
                if (binCount >= TREEIFY_THRESHOLD)
                    treeifyBin(tab, i);
                if (oldVal != null)
                    return oldVal;
                break;
            }
        }
    }
    addCount(1L, binCount);
    return null;
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764122379976-80a235e0-61f8-401d-bcf0-d26c0d8e3fdc.gif)

 	

1. 根据 key 计算出 hashcode 。

 	

1. 判断是否需要进行初始化。

 	

1. 即为当前 key 定位出的 Node，如果为空表示当前位置可以写入数据，利用 CAS 尝试写入，失败则自旋保证成功。

 	

1. 如果当前位置的 `hashcode == MOVED == -1`,则需要进行扩容。

 	

1. 如果都不满足，则利用 synchronized 锁写入数据。

 	

1. 如果数量大于 `TREEIFY_THRESHOLD` 则要执行树化方法，在 `treeifyBin` 中会首先判断当前数组长度 ≥64 时才会将链表转换为红黑树。

```plain
public V get(Object key) {
    Node<K,V>[] tab; Node<K,V> e, p; int n, eh; K ek;
    // key 所在的 hash 位置
    int h = spread(key.hashCode());
    if ((tab = table) != null && (n = tab.length) > 0 &&
        (e = tabAt(tab, (n - 1) & h)) != null) {
        // 如果指定位置元素存在，头结点hash值相同
        if ((eh = e.hash) == h) {
            if ((ek = e.key) == key || (ek != null && key.equals(ek)))
                // key hash 值相等，key值相同，直接返回元素 value
                return e.val;
        }
        else if (eh < 0)
            // 头结点hash值小于0，说明正在扩容或者是红黑树，find查找
            return (p = e.find(h, key)) != null ? p.val : null;
        while ((e = e.next) != null) {
            // 是链表，遍历查找
            if (e.hash == h &&
                ((ek = e.key) == key || (ek != null && key.equals(ek))))
                return e.val;
        }
    }
    return null;
}
```

![img](https://cdn.nlark.com/yuque/0/2025/gif/53862437/1764122380606-059cb298-20fa-4145-9164-1783866828ca.gif)



### 面试题

#### 1. HashMap中hash函数是怎么实现的？还有哪些hash函数的实现方式？

对于key的hashCode做hash操作，无符号右移16位然后做异或运算。

```plain
    static final int hash(Object key) {
        int h;
        return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
    }
```

平方取中法，伪随机数法和取余数法。

#### 2. 当两个对象的hashCode相等时会怎么样？

会产生哈希碰撞，若key值内容相同则替换旧的value.不然连接到链表后面，链表长度超过阈值8就转换为红黑树存储。

#### 3. 何时发生哈希碰撞和什么是哈希碰撞,如何解决哈希碰撞？

只要两个元素的key计算的哈希码值相同就会发生哈希碰撞。jdk8前使用链表解决哈希碰撞。jdk8之后使用链表+红黑树解决哈希碰撞。

#### 4. 如果两个键的hashcode相同，如何存储键值对？

hashcode相同，通过equals比较内容是否相同。

相同：则新的value覆盖之前的value

不相同：则将新的键值对添加到哈希表中

#### 5. 为什么必须是2的n次幂？如果输入值不是2的幂比如10会怎么样？

原因：为了提升效率 —— 通过位运算代替取模运算。

定位桶位置

```java
index = (n - 1) & hash
```

只有当 n 为 2k 时，n - 1 为连续的 1。结果为保留 hash 值的后 k - 1 位。

不是 2 的幂会加剧哈希冲突，这时候保留位数减少，信息量越少。

通过 tableSizeFor()函数返回比 10 大的最小 2 的幂

#### 6. 为什么Map桶中节点个数超过8才转为红黑树？

平衡空间占用 + 时间效率

链表遍历，时间复杂度为 O(n), 红黑树遍历，事件复杂度为 O(logn)。

为什么是 8？

JDK 作者实测经验值

太小频繁树化浪费性能，太大链表查询慢

哈希表默认负载因子是 0.75，红黑树触发前通常已经有很多键值分散在不同桶。

#### 7. 什么时候才需要扩容

size > capacity * loadFactor

#### 8. HashMap的扩容是什么？

创建更大数组 + 重新分配所有节点位置



#### 9. 如何设计多个非重复的键值对要存储 HashMap 的初始化？

建议初始化时，指定集合初始值大小。

HashMap 每次扩容都需要重建 hash 表，影响性能。

使用 **initialCapacity/ 0.75F + 1.0F** 计算

## 