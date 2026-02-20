# streaming_app.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, window, avg, min, max, count, to_json, struct
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType
)

# ─── 1. SparkSession ────────────────────────────────────────────────────────
spark = SparkSession.builder \
    .appName("CryptoStreamingAggregator") \
    .config("spark.sql.shuffle.partitions", "2") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# ─── 2. JSON Schema ─────────────────────────────────────────────────────────
schema = StructType([
    StructField("symbol",     StringType(), True),
    StructField("price",      DoubleType(), True),
    StructField("event_time", StringType(), True)
])

# ─── 3. Read from Kafka (raw events) ────────────────────────────────────────
raw_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "crypto-topic") \
    .option("startingOffsets", "latest") \
    .load()

# ─── 4. Parse JSON ──────────────────────────────────────────────────────────
crypto_df = raw_df \
    .selectExpr("CAST(value AS STRING) as json_str") \
    .select(from_json(col("json_str"), schema).alias("data")) \
    .select(
        col("data.symbol"),
        col("data.price"),
        col("data.event_time").cast(TimestampType()).alias("event_time")
    )

# ─── 5. Watermark + Sliding Window Aggregations ─────────────────────────────
# Watermark: tolerate late events up to 2 minutes
# Sliding window: 5-minute window, sliding every 1 minute
agg_df = crypto_df \
    .withWatermark("event_time", "2 minutes") \
    .groupBy(
        window(col("event_time"), "5 minutes", "1 minute"),
        col("symbol")
    ) \
    .agg(
        avg("price").alias("avg_price"),
        min("price").alias("min_price"),
        max("price").alias("max_price"),
        count("price").alias("count")
    ) \
    .select(
        col("symbol"),
        col("avg_price"),
        col("min_price"),
        col("max_price"),
        col("count"),
        col("window.start").cast(StringType()).alias("window_start"),
        col("window.end").cast(StringType()).alias("window_end")
    )

# ─── 6. Serialize to JSON for Kafka output ──────────────────────────────────
kafka_output = agg_df.select(
    to_json(struct(
        col("symbol"),
        col("avg_price"),
        col("min_price"),
        col("max_price"),
        col("count"),
        col("window_start"),
        col("window_end")
    )).alias("value")
)

# ─── 7. Write aggregates to Kafka topic ─────────────────────────────────────
query = kafka_output.writeStream \
    .outputMode("update") \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("topic", "crypto-aggregates") \
    .option("checkpointLocation", "./checkpoints/crypto-aggregates") \
    .trigger(processingTime="10 seconds") \
    .start()

print("✅ Streaming started — aggregates flowing into 'crypto-aggregates' topic.")
print("   Window: 5 min sliding every 1 min | Watermark: 2 min | Trigger: 10s")

query.awaitTermination()