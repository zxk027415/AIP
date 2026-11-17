# @AI_GENERATED: Kiro v1.0
"""
将工作流模板和 Skills 从 JSON 文件迁移到数据库
"""
import sys
import os
import json

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from database import SessionLocal, init_db
from models.algo_template import WorkflowTemplate, Skill


def migrate_workflow_templates():
    """迁移工作流模板"""
    json_path = os.path.join(backend_dir, "data/workflow_templates/templates.json")
    
    if not os.path.exists(json_path):
        print(f"❌ 文件不存在: {json_path}")
        return 0
    
    with open(json_path, "r", encoding="utf-8") as f:
        templates = json.load(f)
    
    db = SessionLocal()
    count = 0
    
    try:
        for tpl in templates:
            # 检查是否已存在
            existing = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == tpl["id"]).first()
            if existing:
                print(f"  ⏭️ 跳过已存在: {tpl['id']}")
                continue
            
            # 创建新记录
            record = WorkflowTemplate(
                id=tpl["id"],
                name=tpl["name"],
                description=tpl.get("description"),
                scenario_id=tpl.get("scenario_id"),
                scenario_name=tpl.get("scenario_name"),
                category=tpl.get("category"),
                status=tpl.get("status", "draft"),
                version=tpl.get("version", "v1.0.0"),
                author=tpl.get("author"),
                node_count=tpl.get("node_count", 0),
                edge_count=tpl.get("edge_count", 0),
                usage_count=tpl.get("usage_count", 0),
                star_count=tpl.get("star_count", 0),
                is_starred=tpl.get("is_starred", False),
                tags=tpl.get("tags"),
            )
            db.add(record)
            count += 1
            print(f"  ✅ 导入: {tpl['name']}")
        
        db.commit()
        print(f"\n工作流模板导入完成: {count} 条")
        return count
        
    except Exception as e:
        db.rollback()
        print(f"❌ 导入失败: {e}")
        return 0
    finally:
        db.close()


def migrate_skills():
    """迁移 Skills"""
    json_path = os.path.join(backend_dir, "data/skills/packaged_skills.json")
    
    if not os.path.exists(json_path):
        print(f"❌ 文件不存在: {json_path}")
        return 0
    
    with open(json_path, "r", encoding="utf-8") as f:
        skills = json.load(f)
    
    db = SessionLocal()
    count = 0
    
    try:
        for s in skills:
            skill_id = s.get("skill_id") or s.get("id")
            
            # 检查是否已存在
            existing = db.query(Skill).filter(Skill.id == skill_id).first()
            if existing:
                print(f"  ⏭️ 跳过已存在: {skill_id}")
                continue
            
            # 解析配置
            training_config = s.get("training_config", {})
            resource_config = s.get("resource_config", {})
            
            # 创建新记录
            record = Skill(
                id=skill_id,
                skill_name=s.get("skill_name"),
                skill_version=s.get("skill_version", "1.0.0"),
                description=s.get("description"),
                source_template_id=s.get("source_template_id"),
                source_template_name=s.get("source_template_name"),
                source_template_version=s.get("source_template_version"),
                training_enabled=training_config.get("enabled", True),
                training_min_samples=training_config.get("min_samples", 30),
                training_default_epochs=training_config.get("default_epochs", 80),
                training_default_batch_size=training_config.get("default_batch_size", 32),
                resource_cpu=resource_config.get("cpu", "2"),
                resource_memory=resource_config.get("memory", "4Gi"),
                resource_gpu=resource_config.get("gpu", "optional"),
                resource_timeout=resource_config.get("timeout_seconds", 300),
                status=s.get("status", "packaged"),
                created_by=s.get("created_by", "system"),
            )
            db.add(record)
            count += 1
            print(f"  ✅ 导入: {s.get('skill_name')}")
        
        db.commit()
        print(f"\nSkills 导入完成: {count} 条")
        return count
        
    except Exception as e:
        db.rollback()
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return 0
    finally:
        db.close()


def main():
    print("=" * 60)
    print("工作流模板和 Skills 数据库迁移")
    print("=" * 60)
    
    # 初始化数据库（创建表）
    print("\n1. 初始化数据库...")
    init_db()
    print("   ✅ 数据库表已创建")
    
    # 迁移工作流模板
    print("\n2. 迁移工作流模板...")
    wf_count = migrate_workflow_templates()
    
    # 迁移 Skills
    print("\n3. 迁移 Skills...")
    skill_count = migrate_skills()
    
    # 统计
    print("\n" + "=" * 60)
    print("迁移完成!")
    print(f"  工作流模板: {wf_count} 条")
    print(f"  Skills: {skill_count} 条")
    print("=" * 60)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
