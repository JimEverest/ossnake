import unittest
import sys
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('TestRunner')

def run_aliyun_advanced_test(test_name=None):
    """运行阿里云高级测试
    
    Args:
        test_name: 要运行的具体测试方法名，如果为None则运行所有测试
    """
    from tests.test_advanced_ali import AliyunAdvancedTests
    
    # 创建测试套件
    suite = unittest.TestSuite()
    
    if test_name:
        # 运行指定的测试方法
        suite.addTest(AliyunAdvancedTests(test_name))
    else:
        # 运行所有测试
        tests = unittest.TestLoader().loadTestsFromTestCase(AliyunAdvancedTests)
        suite.addTests(tests)
    
    # 运行测试
    logger.info(f"=== 开始运行阿里云高级测试 {test_name or 'all'} ===")
    start_time = datetime.now()
    
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout
    )
    result = runner.run(suite)
    
    # 输出测试结果摘要
    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"""
测试完成:
运行时间: {duration:.2f} 秒
运行数量: {result.testsRun}
成功: {result.testsRun - len(result.failures) - len(result.errors)}
失败: {len(result.failures)}
错误: {len(result.errors)}
    """)
    
    return result

if __name__ == '__main__':
    # 运行所有测试
    # run_aliyun_advanced_test()
    
    # 或运行特定测试
    run_aliyun_advanced_test('test_concurrent_uploads') 