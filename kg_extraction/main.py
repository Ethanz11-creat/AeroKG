import argparse
import asyncio
import logging
import sys
import time
from typing import Optional

from .loader import ChunkLoader
from .cleaner import TextCleaner
from .classifier import ChunkClassifier
from .normalizer import Normalizer
from .extractor import KnowledgeExtractor
from .async_extractor import AsyncKnowledgeExtractor, AsyncLLMProvider
from .validator import Validator
from .llm_provider import LLMProvider
from .exporter import KGExporter
from .config import get_api_key, SILICONFLOW_MODEL, SILICONFLOW_BASE_URL, LLM_TIMEOUT


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_pipeline(
    input_path: str,
    output_dir: str = "kg_output",
    api_key: str = "",
    model: str = "",
    base_url: str = "",
    delay_seconds: float = 0.3,
    max_retries: int = 2,
    limit: int = 0,
    use_async: bool = True,
    batch_size: int = 10,
    max_concurrency: int = 5,
    verbose: bool = False,
) -> dict:
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    total_start = time.time()

    mode_str = "Async" if use_async else "Sync"
    logger.info("=" * 60)
    logger.info(f"民航法规知识图谱抽取 Pipeline 启动 ({mode_str} LLM-first 模式)")
    logger.info("=" * 60)

    effective_api_key = api_key or get_api_key()
    effective_model = model or SILICONFLOW_MODEL
    effective_base_url = base_url or SILICONFLOW_BASE_URL

    if not effective_api_key:
        logger.error("错误: 未配置 API Key!")
        logger.error("请通过以下方式之一提供 API Key:")
        logger.error("  1. 命令行参数: --api-key YOUR_KEY")
        logger.error("  2. 环境变量: set SILICONFLOW_API_KEY=YOUR_KEY")
        logger.error("  3. 修改 kg_extraction/config.py 中的 SILICONFLOW_API_KEY")
        return {"status": "error", "message": "API Key not configured"}

    logger.info(f"[1/7] 加载输入文件: {input_path}")
    loader = ChunkLoader(input_path)
    chunks = loader.load()

    logger.info(f"[2/7] 文本清洗与过滤 (规则仅用于清洗和过滤)")
    cleaner = TextCleaner()
    passed_chunks, stats = ChunkClassifier.filter_and_validate(chunks, cleaner)
    
    if limit > 0:
        passed_chunks = passed_chunks[:limit]
        logger.info(f"  限制抽取数量: {limit}")
    
    logger.info(f"  总 chunk 数: {stats['total']}")
    logger.info(f"  过滤后通过: {stats['passed']}")
    logger.info(f"  过滤数: {stats['total'] - stats['passed']}")
    logger.info(f"  定义类 chunk: {stats.get('definition_chunks', 0)}")
    logger.info(f"  规则类 chunk: {stats.get('rule_chunks', 0)}")
    logger.info(f"  条件类 chunk: {stats.get('condition_chunks', 0)}")
    logger.info(f"  suspicious: {stats.get('suspicious', 0)}")
    logger.info(f"  review_required: {stats.get('review_required', 0)}")

    logger.info(f"[3/7] 初始化 LLM Provider ({mode_str})")
    logger.info(f"  API Base URL: {effective_base_url}")
    logger.info(f"  Model: {effective_model}")
    if use_async:
        logger.info(f"  Batch Size: {batch_size}, Max Concurrency: {max_concurrency}")

    if use_async:
        llm_stats, results, failed_cases, extractor_stats = asyncio.run(
            _run_async_extraction(
                passed_chunks=passed_chunks,
                api_key=effective_api_key,
                base_url=effective_base_url,
                model=effective_model,
                batch_size=batch_size,
                max_concurrency=max_concurrency,
                max_retries=max_retries,
                logger=logger,
            )
        )
    else:
        llm_provider = LLMProvider(
            api_key=effective_api_key,
            base_url=effective_base_url,
            model=effective_model,
        )

        if not llm_provider.is_enabled:
            logger.error("LLM Provider 初始化失败!")
            return {"status": "error", "message": "LLM Provider initialization failed"}

        estimated_time = len(passed_chunks) * delay_seconds / 60
        logger.info(f"[4/7] LLM 知识抽取 (预计耗时: {estimated_time:.1f} 分钟)")
        logger.info(f"  注意: 所有实体/规则/条件/约束均由 LLM 抽取，规则仅用于清洗/过滤/校验/归一化")
        extractor = KnowledgeExtractor(llm_provider=llm_provider)
        llm_stats = extractor.extract_all_with_llm(
            passed_chunks,
            delay_seconds=delay_seconds,
            max_retries=max_retries,
        )
        results = extractor.get_results()
        failed_cases = extractor.get_failed_cases()
        extractor_stats = extractor.get_stats()

    logger.info(f"  LLM 成功: {llm_stats.get('llm_success', 0)}")
    logger.info(f"  LLM 失败: {llm_stats.get('llm_failed', 0)}")
    if use_async:
        logger.info(f"  缓存命中: {llm_stats.get('cache_hits', 0)}")
        logger.info(f"  缓存未命中: {llm_stats.get('cache_misses', 0)}")

    logger.info(f"[5/7] 结果验证 (规则仅用于校验)")
    validator = Validator()
    validation_result = validator.validate_results(results)
    logger.info(f"  验证结果: {'PASS' if validation_result['is_valid'] else 'FAIL'}")
    logger.info(f"  警告数: {validation_result['warning_count']}")
    for w in validation_result["warnings"][:10]:
        logger.warning(f"  - {w}")

    logger.info(f"[6/7] 导出结果到: {output_dir}")
    exporter = KGExporter(output_dir)
    export_path = exporter.export(results, stats, llm_stats, extractor_stats, failed_cases)
    logger.info(f"  导出完成: {export_path}")

    total_elapsed = time.time() - total_start
    logger.info(f"[7/7] Pipeline 完成! 耗时: {total_elapsed:.2f}s")
    logger.info("=" * 60)

    summary = {
        "status": "success",
        "elapsed_seconds": round(total_elapsed, 2),
        **stats,
        "output_dir": export_path,
        "llm_stats": llm_stats,
        "extractor_stats": extractor_stats,
        "extraction_counts": {
            "documents": len(results.get("documents", [])),
            "structural_units": len(results.get("structural_units", [])),
            "terms": len(results.get("terms", [])),
            "definitions": len(results.get("definitions", [])),
            "rules": len(results.get("rules", [])),
            "conditions": len(results.get("conditions", [])),
            "constraints": len(results.get("constraints", [])),
            "references": len(results.get("references", [])),
            "edges": len(results.get("edges", [])),
        },
        "validation": validation_result,
    }

    return summary


async def _run_async_extraction(
    passed_chunks: list,
    api_key: str,
    base_url: str,
    model: str,
    batch_size: int,
    max_concurrency: int,
    max_retries: int,
    logger: logging.Logger,
):
    logger.info(f"[4/7] Async LLM 知识抽取")
    logger.info(f"  注意: 所有实体/规则/条件/约束均由 LLM 抽取，规则仅用于清洗/过滤/校验/归一化")
    
    async with AsyncLLMProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_concurrency=max_concurrency,
        max_retries=max_retries,
        timeout=LLM_TIMEOUT,
    ) as llm_provider:
        extractor = AsyncKnowledgeExtractor(
            llm_provider=llm_provider,
            merge_short_chunks=True,
            short_chunk_threshold=100,
        )
        llm_stats = await extractor.extract_all_async(
            passed_chunks,
            batch_size=batch_size,
        )
        results = extractor.get_results()
        failed_cases = extractor.get_failed_cases()
        extractor_stats = extractor.get_stats()
    
    return llm_stats, results, failed_cases, extractor_stats


def main():
    parser = argparse.ArgumentParser(
        description="民航法规知识图谱抽取器 - LLM-first 模式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python -m kg_extraction.main --input chunks.json
  python -m kg_extraction.main --input chunks.json --limit 50
  python -m kg_extraction.main --input chunks.json --batch-size 10 --max-concurrency 5
  python -m kg_extraction.main --input chunks.json --no-async

架构说明:
  - 主抽取方式: LLM (DeepSeek-V3)
  - 规则仅用于: 文本清洗、噪声过滤、输出校验、术语归一化
  - 规则不用于: subject/action/object 抽取、规则三元组生成
  - 默认使用异步并发模式，可大幅提升抽取速度

配置说明:
  --api-key       硅基流动 API Key (也可通过环境变量 SILICONFLOW_API_KEY 设置)
  --model         模型名称，默认 deepseek-ai/DeepSeek-V3
  --base-url      API 地址，默认 https://api.siliconflow.cn/v1
  --batch-size    异步模式下每批处理的 chunk 数 (默认: 10)
  --max-concurrency 异步模式下最大并发数 (默认: 5)
        """,
    )
    parser.add_argument("--input", "-i", required=True, help="输入 chunks.json 文件路径")
    parser.add_argument("--output", "-o", default="kg_output", help="输出目录 (默认: kg_output)")
    parser.add_argument("--api-key", default="", help="硅基流动 API Key")
    parser.add_argument("--model", default="", help="LLM 模型名 (默认: deepseek-ai/DeepSeek-V3)")
    parser.add_argument("--base-url", default="", help="LLM API Base URL (默认: https://api.siliconflow.cn/v1)")
    parser.add_argument("--delay", type=float, default=0.3, help="同步模式下 LLM 调用间隔秒数 (默认: 0.3)")
    parser.add_argument("--max-retries", type=int, default=2, help="LLM 调用失败重试次数 (默认: 2)")
    parser.add_argument("--limit", type=int, default=0, help="限制抽取的 chunk 数量 (默认: 0 表示不限制)")
    parser.add_argument("--no-async", action="store_true", help="禁用异步模式，使用同步串行模式")
    parser.add_argument("--batch-size", type=int, default=10, help="异步模式下每批处理的 chunk 数 (默认: 10)")
    parser.add_argument("--max-concurrency", type=int, default=5, help="异步模式下最大并发数 (默认: 5)")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    try:
        summary = run_pipeline(
            input_path=args.input,
            output_dir=args.output,
            api_key=args.api_key,
            model=args.model,
            base_url=args.base_url,
            delay_seconds=args.delay,
            max_retries=args.max_retries,
            limit=args.limit,
            use_async=not args.no_async,
            batch_size=args.batch_size,
            max_concurrency=args.max_concurrency,
            verbose=args.verbose,
        )

        if summary.get("status") == "error":
            print(f"\n错误: {summary.get('message', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        print("\n" + "=" * 60)
        print("LLM-first 抽取完成！统计摘要:")
        print("=" * 60)
        ec = summary.get("extraction_counts", {})
        ls = summary.get("llm_stats", {})
        es = summary.get("extractor_stats", {})
        print(f"  总 chunk 数:         {summary.get('total', 0)}")
        print(f"  过滤数:             {summary.get('total', 0) - summary.get('passed', 0)}")
        print(f"  通过数:             {summary.get('passed', 0)}")
        print(f"  LLM 成功:           {ls.get('llm_success', 0)}")
        print(f"  LLM 失败:           {ls.get('llm_failed', 0)}")
        if ls.get("cache_hits"):
            print(f"  缓存命中:           {ls.get('cache_hits', 0)}")
        print("-" * 60)
        print(f"  抽取 Term 数:       {ec.get('terms', 0)}")
        print(f"  抽取 Definition 数: {ec.get('definitions', 0)}")
        print(f"  抽取 Rule 数:       {ec.get('rules', 0)}")
        print(f"  抽取 Condition 数:  {ec.get('conditions', 0)}")
        print(f"  抽取 Constraint 数: {ec.get('constraints', 0)}")
        print(f"  抽取 Reference 数:  {ec.get('references', 0)}")
        print(f"  边数量:             {ec.get('edges', 0)}")
        print("-" * 60)
        print(f"  平均延迟:           {es.get('avg_latency_ms', 0):.1f} ms")
        print(f"  失败案例数:         {es.get('failed_case_count', 0)}")
        print(f"  输出目录:           {summary.get('output_dir', '')}")
        print(f"  总耗时:             {summary.get('elapsed_seconds', 0):.1f}s")
        print("=" * 60)
    except FileNotFoundError as e:
        print(f"错误: 文件未找到 - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
