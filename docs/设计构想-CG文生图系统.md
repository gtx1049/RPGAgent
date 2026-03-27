# 设计构想：文生图CG生成系统

> 创建时间：2026-03-27
> 状态：待实现

---

## 核心目标

通过 AI 文生图服务，根据场景内容自动生成游戏 CG 插画，提升游戏沉浸感。

---

## 服务商选择

| 服务 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **通义万相** | 国内可用、成本低、API 稳定 | 风格偏中式 | ⭐⭐⭐⭐ |
| **文心一格** | 国内可用、百度生态 | 版权限制 | ⭐⭐⭐ |
| **Stable Diffusion** | 开源、本地部署、可控性强 | 需要 GPU 资源 | ⭐⭐⭐⭐⭐ (自部署) |
| **DALL-E 3** | 质量高、GPT-4 优化 | 成本高 | ⭐⭐⭐ |
| **ComfyUI API** | 灵活、工作流可定制 | 配置复杂 | ⭐⭐ |

---

## 系统架构

```
rpgagent/systems/image_generator.py
│
├── ImageGenerator (抽象基类)
│   ├── StableDiffusionGenerator
│   ├── TongyiWanxiangGenerator
│   ├── DalleGenerator
│   └── ... (可扩展)
│
├── CGTriggerConfig (场景CG触发配置)
│   └── scenes/
│       └── {scene_id}.yaml (每个场景的CG配置)
│
└── CGCache (本地缓存管理)
    └── ~/.cache/rpgagent/cg/
```

---

## 核心接口

```python
# rpgagent/systems/image_generator.py

class ImageGenerator:
    """文生图生成器基类"""
    
    def __init__(self, config: dict):
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url")
        self.default_style = config.get("style", "fantasy watercolor")
        self.cache_dir = config.get("cache_dir", "~/.cache/rpgagent/cg")
    
    async def generate_scene_cg(
        self,
        scene_id: str,
        scene_content: str,
        characters: list[str] = None,
        style: str = None,
        **kwargs
    ) -> str:
        """
        根据场景内容生成CG图
        
        Args:
            scene_id: 场景ID
            scene_content: 场景文本内容
            characters: 场景中的角色列表
            style: 艺术风格
            
        Returns:
            本地缓存的图片路径
        """
        # 1. 构建 Prompt
        prompt = self._build_prompt(scene_content, characters, style)
        
        # 2. 调用 API 生成
        image_data = await self._call_api(prompt, **kwargs)
        
        # 3. 缓存到本地
        cached_path = self._cache_image(scene_id, image_data)
        
        return cached_path
    
    def _build_prompt(
        self,
        scene_content: str,
        characters: list[str] = None,
        style: str = None
    ) -> str:
        """从场景内容构建生成Prompt"""
        # 提取场景关键元素
        elements = self._extract_elements(scene_content)
        
        # 构建风格化描述
        style_desc = self._get_style_description(style)
        
        # 组合 Prompt
        prompt = f"{elements}, {style_desc}, detailed, high quality"
        
        return prompt
    
    def _extract_elements(self, scene_content: str) -> str:
        """从场景内容提取关键视觉元素"""
        # TODO: 可以用 LLM 辅助提取
        # 目前简单实现：提取名词和场景描述
        pass
```

---

## 场景CG配置

每个剧本场景可以配置 CG 生成规则：

```yaml
# games/{game_id}/scenes/{scene_id}.cg.yaml

scene_id: forest_edge
trigger:
  type: auto       # auto | manual | milestone
  condition: null   # 触发条件（可选）

style:
  default: "fantasy illustration, dark atmosphere"
  variations:
    - "watercolor painting style"
    - "oil painting style"
    
characters:
  - name: "大灰狼"
    appearance: "big bad wolf, grey fur, menacing eyes"
  - name: "猪大哥"
    appearance: "little pig, chubby, pink skin"

generation:
  aspect_ratio: "16:9"
  resolution: [1920, 1080]
  seed: null  # 固定种子可复现
  
cache:
  enabled: true
  ttl_hours: 168  # 缓存有效期（7天）
```

---

## 配置示例

```yaml
# rpgagent/config/image_generators.yaml

providers:
  tongyi:
    enabled: true
    api_key: "${TONGYI_API_KEY}"
    api_url: "https://dashscope.aliyuncs.com/api/v1/images/generations"
    style: "fantasy illustration"
    default_size: "1024*1024"
    
  stable_diffusion:
    enabled: false
    api_url: "http://localhost:7860/sdapi/v1/txt2img"
    model: "AnythingV5"
    steps: 25
    
  dalle:
    enabled: false
    api_key: "${OPENAI_API_KEY}"
    model: "dall-e-3"
    size: "1024x1024"

cache:
  enabled: true
  directory: "~/.cache/rpgagent/cg"
  max_size_mb: 500
  
trigger:
  # 关键场景自动生成CG
  auto_trigger_scenes:
    - "boss_fight"
    - "ending"
    - "important_choice"
    
  # 玩家手动触发
  manual_enabled: true
```

---

## 前端集成

```javascript
// static/js/game.js

class CGallery {
    constructor() {
        this.currentCG = null;
        this.cgContainer = document.getElementById('cg-container');
    }
    
    async showSceneCG(sceneId, imageUrl) {
        // 显示CG动画效果
        this.cgContainer.innerHTML = `
            <div class="cg-overlay">
                <img src="${imageUrl}" alt="场景CG" class="scene-cg" />
                <button class="cg-close">关闭</button>
            </div>
        `;
        
        // 淡入效果
        this.cgContainer.querySelector('.cg-overlay').classList.add('fade-in');
    }
    
    hideCG() {
        this.cgContainer.innerHTML = '';
    }
}
```

---

## CSS 样式

```css
/* static/css/game.css */

.cg-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.9);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.5s ease;
}

.scene-cg {
    max-width: 90%;
    max-height: 80%;
    border-radius: 8px;
    box-shadow: 0 0 30px rgba(0, 0, 0, 0.5);
}

.cg-close {
    margin-top: 20px;
    padding: 10px 30px;
    background: var(--primary-color);
    border: none;
    border-radius: 4px;
    color: white;
    cursor: pointer;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
```

---

## 实现计划

1. **Phase 1: 基础框架**
   - [ ] 定义 ImageGenerator 抽象基类
   - [ ] 实现 TongyiWanxiangGenerator（通义万相）
   - [ ] 添加本地缓存机制

2. **Phase 2: 场景集成**
   - [ ] 设计场景CG配置格式
   - [ ] 在 GameMaster 中集成 CG 触发
   - [ ] 支持自动/手动触发模式

3. **Phase 3: 前端展示**
   - [ ] CG 画廊组件
   - [ ] 淡入动画效果
   - [ ] CG 历史查看功能

4. **Phase 4: 扩展支持**
   - [ ] 添加 Stable Diffusion 支持
   - [ ] 添加 DALL-E 支持
   - [ ] 支持自定义风格模型
