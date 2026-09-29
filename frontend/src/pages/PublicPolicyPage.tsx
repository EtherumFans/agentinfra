import { Link } from 'react-router-dom';

export default function PublicPolicyPage({ kind }: { kind: 'privacy' | 'terms' }) {
  return <main className="min-h-dvh bg-background text-foreground p-6">
    <article className="mx-auto max-w-2xl space-y-6">
      <Link to="/login" className="text-primary underline">返回登录</Link>
      <h1 className="text-2xl font-bold">{kind === 'privacy' ? '隐私与数据处理说明' : '服务使用说明'}</h1>
      <p>本说明适用于当前开发候选版本。正式部署的运营主体、联系方式、处理依据、保留期限与服务承诺须由部署方在上线前提供。</p>
      {kind === 'privacy' ? <>
        <p>平台处理账户、组织成员关系、用户提交的文本及运行记录。启用外部模型或连接器时，输入可能交由所配置的服务处理；请先向管理员确认服务提供方、存储地区与保留设置。</p>
        <p>开发环境仅使用合成或经过授权的去标识资料。不要提交真实患者身份信息。持久记忆需要独立用途授权，用户授权按钮不代表已取得患者或医院授权。</p>
        <p>如需查询、更正或删除资料，请联系当前部署的管理员。实际删除、审计和备份保留范围以部署配置及适用协议为准。</p>
      </> : <>
        <p>当前结果用于开发验证和辅助复核，需由具备相应资质的人员检查证据与适用范围。规则通过不代表临床正确，不可直接作为诊断、正式编码或医保结算依据。</p>
        <p>模型、语音和第三方资产需分别配置及取得授权。页面显示的估算费用、开发账本和实际供应商账单不同，当前不提供正式支付、发票或生产服务等级承诺。</p>
        <p>请仅在获得授权的组织和用途内使用账户及API凭据。医院上线须另外完成数据治理、基础设施和业务验收。</p>
      </>}
      <p className="text-sm text-muted-foreground">此处公开说明当前产品边界，不代替部署方的正式隐私政策或服务合同。</p>
    </article>
  </main>;
}
