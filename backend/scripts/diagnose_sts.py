#!/usr/bin/env python3
"""
诊断 STS Token 生成问题

排查步骤：
1. 验证基本配置（Access Key, Region, Role ARN）
2. 测试 Access Key 有效性
3. 测试 RAM 角色是否存在
4. 测试 AssumeRole 权限
5. 测试信任策略配置
6. 给出具体修复建议
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdksts.request.v20150401 import AssumeRoleRequest
import oss2

from app.config import settings


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_check(name: str, status: bool, details: str = ""):
    """打印检查结果"""
    symbol = "✅" if status else "❌"
    print(f"{symbol} {name}")
    if details:
        print(f"   {details}")


def check_basic_config():
    """检查基本配置"""
    print_section("1. 基本配置检查")

    checks = {
        "OSS Access Key ID": settings.oss_access_key_id,
        "OSS Access Key Secret": settings.oss_access_key_secret,
        "OSS Region": settings.oss_region,
        "RAM Role ARN": settings.aliyun_role_arn,
        "OSS Endpoint": settings.oss_endpoint,
        "OSS Bucket": settings.oss_bucket_name,
    }

    all_ok = True
    for name, value in checks.items():
        is_valid = value and value != "dummy" and len(str(value)) > 0
        print_check(
            name,
            is_valid,
            f"{value[:20]}..." if is_valid else "未配置或使用占位符"
        )
        all_ok = all_ok and is_valid

    return all_ok


def check_access_key_validity():
    """检查 Access Key 有效性"""
    print_section("2. Access Key 有效性测试")

    try:
        # 使用 OSS 列举 bucket 测试 Access Key
        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket_name)

        # 尝试列举对象
        result = bucket.list_objects(max_keys=1)
        print_check("OSS Access Key 有效", True, "可以访问 OSS Bucket")
        return True

    except oss2.exceptions.NoSuchBucket as e:
        print_check("OSS Access Key 有效", True, f"Access Key 有效，但 Bucket 不存在: {settings.oss_bucket_name}")
        return True

    except oss2.exceptions.AccessDenied as e:
        print_check("OSS Access Key 权限", False, "Access Key 有效但没有 OSS 访问权限")
        return False

    except oss2.exceptions.InvalidAccessKeyId as e:
        print_check("OSS Access Key", False, "Access Key ID 无效")
        return False

    except Exception as e:
        print_check("OSS Access Key 测试", False, f"错误: {str(e)}")
        return False


def check_ram_role_exists():
    """检查 RAM 角色是否存在"""
    print_section("3. RAM 角色存在性检查")

    try:
        client = AcsClient(
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
            settings.oss_region or "cn-shanghai"
        )

        # 使用 CommonRequest 查询角色信息
        request = CommonRequest()
        request.set_domain('ram.aliyuncs.com')
        request.set_version('2015-05-01')
        request.set_action_name('GetRole')
        request.add_query_param('RoleName', 'langear')

        response = client.do_action_with_exception(request)
        response_str = response.decode('utf-8')

        if 'EntityNotExist.Role' in response_str:
            print_check("RAM 角色存在", False, f"角色不存在: langear")
            return False
        else:
            print_check("RAM 角色存在", True, f"角色 ARN: {settings.aliyun_role_arn}")

            # 解析并显示角色信息
            import json
            data = json.loads(response_str)
            if 'Role' in data:
                role = data['Role']
                print(f"   角色名称: {role.get('RoleName')}")
                print(f"   创建时间: {role.get('CreateDate')}")
                print(f"   描述: {role.get('Description', '无')}")
            return True

    except Exception as e:
        error_str = str(e)
        if 'NoPermission' in error_str or 'Forbidden.RAM' in error_str:
            print_check(
                "RAM 角色查询权限",
                False,
                "Access Key 没有查询 RAM 角色的权限（这不影响 AssumeRole）"
            )
            print("   ⚠️  跳过此检查，继续测试 AssumeRole...")
            return True  # 继续下一步测试
        else:
            print_check("RAM 角色查询", False, f"错误: {error_str}")
            return False


def check_assume_role_permission():
    """测试 AssumeRole 权限"""
    print_section("4. AssumeRole 权限测试")

    try:
        client = AcsClient(
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
            settings.oss_region or "cn-shanghai"
        )

        request = AssumeRoleRequest.AssumeRoleRequest()
        request.set_RoleArn(settings.aliyun_role_arn)
        request.set_RoleSessionName("langear-test")
        request.set_DurationSeconds(3600)

        # 尝试 AssumeRole
        response = client.do_action_with_exception(request)

        import json
        data = json.loads(response)

        if 'Credentials' in data:
            creds = data['Credentials']
            print_check("AssumeRole 成功", True, "可以获取临时凭证")
            print(f"   临时 Access Key: {creds['AccessKeyId'][:20]}...")
            print(f"   过期时间: {creds['Expiration']}")
            return True
        else:
            print_check("AssumeRole 响应", False, "响应格式异常")
            return False

    except Exception as e:
        error_str = str(e)
        print_check("AssumeRole", False, f"失败: {error_str}")

        # 分析具体错误
        if 'InvalidAccessKeyId.NotFound' in error_str:
            print("\n❌ 问题诊断: Access Key 不存在或未激活")
            print("   可能原因:")
            print("   1. Access Key ID 输入错误")
            print("   2. Access Key 已被删除")
            print("   3. Access Key 未激活")

        elif 'NoPermission' in error_str or 'AssumeRole' in error_str:
            print("\n❌ 问题诊断: Access Key 没有 AssumeRole 权限")
            print("   解决方案:")
            print("   1. 登录阿里云 RAM 控制台")
            print("   2. 找到当前 Access Key 对应的用户/角色")
            print("   3. 附加策略: AliyunSTSAssumeRoleAccess")
            print("   或自定义策略:")
            print("   {")
            print('     "Version": "1",')
            print('     "Statement": [{')
            print('       "Effect": "Allow",')
            print('       "Action": "sts:AssumeRole",')
            print(f'       "Resource": "{settings.aliyun_role_arn}"')
            print("     }]")
            print("   }")

        elif 'EntityNotExist' in error_str:
            print("\n❌ 问题诊断: RAM 角色不存在")
            print(f"   角色 ARN: {settings.aliyun_role_arn}")
            print("   解决方案:")
            print("   1. 检查角色名称拼写")
            print("   2. 检查账号 ID 是否正确")
            print("   3. 在 RAM 控制台确认角色存在")

        return False


def check_role_trust_policy():
    """检查角色信任策略"""
    print_section("5. 角色信任策略检查")

    try:
        client = AcsClient(
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
            settings.oss_region or "cn-shanghai"
        )

        # 查询角色信任策略
        request = CommonRequest()
        request.set_domain('ram.aliyuncs.com')
        request.set_version('2015-05-01')
        request.set_action_name('GetRole')
        request.add_query_param('RoleName', 'langear')

        response = client.do_action_with_exception(request)

        import json
        import urllib.parse

        data = json.loads(response.decode('utf-8'))

        if 'Role' in data and 'AssumeRolePolicyDocument' in data['Role']:
            policy_encoded = data['Role']['AssumeRolePolicyDocument']
            policy_str = urllib.parse.unquote(policy_encoded)
            policy = json.loads(policy_str)

            print_check("信任策略存在", True, "")
            print("\n   当前信任策略:")
            print(f"   {json.dumps(policy, indent=2, ensure_ascii=False)}")

            # 检查是否允许 AssumeRole
            statements = policy.get('Statement', [])
            has_assume_role = False

            for stmt in statements:
                if stmt.get('Effect') == 'Allow' and 'sts:AssumeRole' in stmt.get('Action', []):
                    has_assume_role = True
                    principal = stmt.get('Principal', {})
                    print(f"\n   ✓ 允许 AssumeRole")
                    print(f"   允许的主体: {principal}")

            if not has_assume_role:
                print_check("信任策略配置", False, "未找到 AssumeRole 授权")

            return has_assume_role
        else:
            print_check("信任策略查询", False, "无法获取信任策略")
            return False

    except Exception as e:
        error_str = str(e)
        if 'NoPermission' in error_str or 'Forbidden' in error_str:
            print_check(
                "信任策略查询权限",
                False,
                "Access Key 没有查询权限（需要 ram:GetRole）"
            )
            print("   ⚠️  无法检查信任策略，但不影响 AssumeRole 功能")
            return True
        else:
            print_check("信任策略查询", False, f"错误: {error_str}")
            return False


def provide_recommendations(results: dict):
    """提供修复建议"""
    print_section("🔧 修复建议")

    if all(results.values()):
        print("✅ 所有检查通过！STS Token 生成应该可以正常工作。")
        print("\n如果仍然有问题，请检查:")
        print("1. 后端服务是否已重启")
        print("2. .env 文件配置是否已生效")
        print("3. 尝试重新运行: uv run uvicorn app.main:app --reload")
        return

    print("根据诊断结果，需要修复以下问题:\n")

    if not results.get('basic_config'):
        print("❌ 配置问题:")
        print("   → 检查 backend/.env 文件，确保所有 OSS 和 RAM 配置项正确填写")
        print("   → 不要使用 'dummy' 占位符\n")

    if not results.get('access_key'):
        print("❌ Access Key 问题:")
        print("   → 登录阿里云控制台")
        print("   → 访问: https://ram.console.aliyun.com/users")
        print("   → 创建新的 Access Key 或检查现有 Key 状态")
        print("   → 确保 Key 已启用\n")

    if not results.get('assume_role'):
        print("❌ AssumeRole 权限问题:")
        print("   → 登录阿里云 RAM 控制台: https://ram.console.aliyun.com")
        print("   → 找到使用当前 Access Key 的 RAM 用户")
        print("   → 点击 '添加权限'")
        print("   → 选择系统策略: AliyunSTSAssumeRoleAccess")
        print("   → 或创建自定义策略允许 sts:AssumeRole 操作\n")
        print("   自定义策略示例:")
        print("   {")
        print('     "Version": "1",')
        print('     "Statement": [{')
        print('       "Effect": "Allow",')
        print('       "Action": "sts:AssumeRole",')
        print(f'       "Resource": "{settings.aliyun_role_arn}"')
        print("     }]")
        print("   }\n")

    if not results.get('trust_policy'):
        print("⚠️  信任策略问题（可能）:")
        print("   → 登录阿里云 RAM 控制台")
        print("   → 进入角色管理: https://ram.console.aliyun.com/roles")
        print("   → 找到角色 'langear'")
        print("   → 点击 '信任策略管理'")
        print("   → 确保信任策略包含以下内容:")
        print("   {")
        print('     "Statement": [{')
        print('       "Effect": "Allow",')
        print('       "Action": "sts:AssumeRole",')
        print('       "Principal": {')
        print('         "RAM": ["acs:ram::1893554225608323:root"]')
        print("       }")
        print("     }]")
        print("   }\n")

    print("\n📚 参考文档:")
    print("   - STS 服务: https://help.aliyun.com/document_detail/28756.html")
    print("   - RAM 角色: https://help.aliyun.com/document_detail/93689.html")
    print("   - AssumeRole API: https://help.aliyun.com/document_detail/28763.html")


def main():
    """主函数"""
    print("\n" + "🔍 " * 20)
    print("  阿里云 STS Token 生成问题诊断工具")
    print("🔍 " * 20)

    results = {}

    # 1. 基本配置检查
    results['basic_config'] = check_basic_config()

    if not results['basic_config']:
        print("\n⚠️  基本配置有问题，请先修复配置后再继续")
        provide_recommendations(results)
        return

    # 2. Access Key 有效性
    results['access_key'] = check_access_key_validity()

    # 3. RAM 角色存在性
    results['role_exists'] = check_ram_role_exists()

    # 4. AssumeRole 权限（核心测试）
    results['assume_role'] = check_assume_role_permission()

    # 5. 信任策略检查（如果有权限）
    if results['role_exists']:
        results['trust_policy'] = check_role_trust_policy()
    else:
        results['trust_policy'] = False

    # 6. 提供修复建议
    provide_recommendations(results)

    # 返回状态码
    if all(results.values()):
        print("\n✅ 诊断完成：所有检查通过")
        sys.exit(0)
    else:
        print("\n❌ 诊断完成：发现问题需要修复")
        sys.exit(1)


if __name__ == "__main__":
    main()
