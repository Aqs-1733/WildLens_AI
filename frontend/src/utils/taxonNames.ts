const cjkPattern = /[\u3400-\u9fff]/
const latinParenPattern = /[（(]\s*[A-Z][A-Za-z.'-]*(?:\s+[a-z][A-Za-z.'-]*){1,4}\s*[）)]/g
const uncertainPattern = /低置信度|待确认|疑似|候选|unknown|unidentified/i

const scientificZh: Record<string, string> = {
  'Ailuropoda melanoleuca': '大熊猫',
  'Alligator sinensis': '扬子鳄',
  'Andrias davidianus': '大鲵',
  'Anas platyrhynchos': '绿头鸭',
  'Apis cerana': '中华蜜蜂',
  'Apis mellifera': '西方蜜蜂',
  'Ardea alba': '大白鹭',
  'Ardea cinerea': '苍鹭',
  'Ardea herodias': '大蓝鹭',
  'Cecropis rufula': '赤腰燕',
  'Cervus nippon': '梅花鹿',
  'Coccinella septempunctata': '七星瓢虫',
  'Elephas maximus': '亚洲象',
  'Elephas maximus indicus': '印度象',
  'Ginkgo biloba': '银杏',
  'Giraffa camelopardalis': '长颈鹿',
  'Grus japonensis': '丹顶鹤',
  'Haliaeetus leucocephalus': '白头海雕',
  'Harmonia axyridis': '异色瓢虫',
  'Hirundo dimidiata': '珍珠胸燕',
  'Hirundo dimidiata marwitzi': '珍珠胸燕马氏亚种',
  'Hirundo rustica': '家燕',
  'Mergus squamatus': '中华秋沙鸭',
  'Nipponia nippon': '朱鹮',
  'Nycticorax nycticorax': '夜鹭',
  'Nycticorax nycticorax nycticorax': '夜鹭指名亚种',
  'Odocoileus virginianus': '白尾鹿',
  'Panthera leo': '狮',
  'Panthera pardus': '金钱豹',
  'Panthera tigris': '虎',
  'Panthera tigris altaica': '东北虎',
  'Panthera tigris tigris': '孟加拉虎',
  'Passer domesticus': '家麻雀',
  'Passer montanus': '树麻雀',
  'Passer montanus kansuensis': '树麻雀甘肃亚种',
  'Phragmites australis': '芦苇',
  'Progne subis': '紫崖燕',
  'Riparia riparia': '崖沙燕',
  'Sciurus carolinensis': '东部灰松鼠',
  'Sturnus vulgaris': '紫翅椋鸟',
  'Sus scrofa': '野猪',
  'Tachycineta albilinea': '红树林燕',
  'Tachycineta bicolor': '树燕',
  'Turdus merula': '乌鸫',
  'Ursus thibetanus': '亚洲黑熊',
  'Vulpes vulpes': '赤狐',
}

const englishZh: Record<string, string> = {
  'amur tiger': '东北虎',
  'asian black bear': '亚洲黑熊',
  'asian elephant': '亚洲象',
  'bald eagle': '白头海雕',
  'bank swallow': '崖沙燕',
  'barn swallow': '家燕',
  'bengal tiger': '孟加拉虎',
  'black-crowned night heron': '夜鹭',
  'chinese alligator': '扬子鳄',
  'chinese giant salamander': '大鲵',
  'crested ibis': '朱鹮',
  'eastern honey bee': '中华蜜蜂',
  'giant panda': '大熊猫',
  giraffe: '长颈鹿',
  ginkgo: '银杏',
  'ginkgo biloba': '银杏',
  leopard: '金钱豹',
  lion: '狮',
  'mangrove swallow': '红树林燕',
  'purple martin': '紫崖燕',
  'red fox': '赤狐',
  'red-crowned crane': '丹顶鹤',
  'scaly-sided merganser': '中华秋沙鸭',
  'sika deer': '梅花鹿',
  tiger: '虎',
  'tree swallow': '树燕',
  'wild boar': '野猪',
}

const categoryZh: Record<string, string> = {
  animal: '动物',
  mammal: '哺乳动物',
  bird: '鸟类',
  reptile: '爬行动物',
  amphibian: '两栖动物',
  fish: '鱼类',
  insect: '昆虫',
  arachnid: '蛛形动物',
  mollusk: '软体动物',
  crustacean: '甲壳动物',
  invertebrate: '无脊椎动物',
  plant: '植物',
  angiosperm: '被子植物',
  gymnosperm: '裸子植物',
  fern: '蕨类植物',
  moss: '苔藓植物',
  algae: '藻类',
  fungus: '真菌',
  lichen: '地衣',
  phenomenon: '自然现象',
  weather: '天气现象',
  fire: '火焰现象',
  smoke: '烟雾现象',
  unknown: '自然目标',
}

function clean(value?: string | null): string {
  return (value || '').replace(/^疑似|^待确认|^低置信度/, '').trim()
}

export function hasChinese(value?: string | null): boolean {
  return cjkPattern.test(value || '')
}

export function cleanChineseDisplayName(value?: string | null, fallback?: string): string {
  const valueUncertain = isUncertainName(value)
  const raw = clean(value).replace(latinParenPattern, '').replace(/\s+/g, ' ').trim()
  if (hasChinese(raw) && !valueUncertain && !isUncertainName(raw)) return raw
  const fallbackText = clean(fallback).replace(latinParenPattern, '').trim()
  if (fallbackText && !isUncertainName(fallbackText)) return fallbackText
  return valueUncertain ? '' : raw
}

export function isUncertainName(value?: string | null): boolean {
  return uncertainPattern.test(value || '')
}

export function categoryNameZh(category?: string | null): string {
  return categoryZh[category || ''] || category || '自然目标'
}

export function localTaxonName({
  label,
  scientificName,
  category,
  fallback,
}: {
  label?: string | null
  scientificName?: string | null
  category?: string | null
  fallback?: string
}): string {
  const labelText = clean(label)
  const scientificText = clean(scientificName)
  const labelUncertain = isUncertainName(label) || isUncertainName(labelText)
  const fallbackText = clean(fallback)
  if (hasChinese(labelText) && !labelUncertain) return labelText
  if (scientificText && scientificZh[scientificText]) return scientificZh[scientificText]
  const baseScientific = scientificText.split(/\s+/).slice(0, 2).join(' ')
  if (baseScientific && scientificZh[baseScientific]) return scientificZh[baseScientific]
  const englishText = labelText.toLowerCase()
  if (!labelUncertain && englishText && englishZh[englishText]) return englishZh[englishText]
  if (scientificText && englishZh[scientificText.toLowerCase()]) return englishZh[scientificText.toLowerCase()]
  if (fallbackText && !isUncertainName(fallbackText)) return fallbackText
  return (!labelUncertain && labelText) || scientificText || categoryZh[category || ''] || '自然目标'
}
