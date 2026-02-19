import discord
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
import asyncio

import os
TOKEN = os.environ.get('TOKEN', 'SEU_TOKEN_AQUI')
STAFF_ROLE_ID = 1463555067129889031
REVIEW_CHANNEL_ID = 1474098859725685056
TICKET_PANEL_CHANNEL_ID = 1463555251226280100

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
open_tickets = {}


# ── MODAL DE AVALIAÇÃO ──────────────────────────────────────────────
class ReviewModal(Modal, title='📝 Avaliação do Atendimento'):
    reason = TextInput(
        label='Conte como foi seu atendimento',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
        placeholder='Descreva como foi o atendimento recebido...'
    )

    def __init__(self, channel_id, staff_id, stars):
        super().__init__()
        self.channel_id = channel_id
        self.staff_id = staff_id
        self.stars = stars

    async def on_submit(self, interaction: discord.Interaction):
        star_display = '⭐' * self.stars if self.stars > 0 else '☆ Nenhuma'
        staff_mention = f'<@{self.staff_id}>' if self.staff_id else '`Não assumido`'

        review_channel = bot.get_channel(REVIEW_CHANNEL_ID)
        if review_channel:
            if self.stars >= 4:
                color = 0x2ECC71
                titulo = '😄 Avaliação Positiva'
            elif self.stars >= 2:
                color = 0xF1C40F
                titulo = '😐 Avaliação Neutra'
            else:
                color = 0xE74C3C
                titulo = '😞 Avaliação Negativa'

            embed = discord.Embed(title=titulo, color=color)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(name='👤 Usuário', value=interaction.user.mention, inline=True)
            embed.add_field(name='🛡️ Staff', value=staff_mention, inline=True)
            embed.add_field(name='⭐ Nota', value=f'{star_display} **({self.stars}/5)**', inline=True)
            embed.add_field(name='💬 Comentário', value=f'>>> {self.reason.value}', inline=False)
            embed.set_footer(text=f'Ticket • {interaction.guild.name}', icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            embed.timestamp = discord.utils.utcnow()
            await review_channel.send(embed=embed)

        await interaction.response.send_message(
            '✅ **Obrigado pelo seu feedback!**\nSua avaliação foi registrada com sucesso.',
            ephemeral=True
        )


# ── SELECT DE ESTRELAS ──────────────────────────────────────────────
class StarSelect(Select):
    def __init__(self, channel_id, staff_id):
        self.channel_id = channel_id
        self.staff_id = staff_id
        options = [
            discord.SelectOption(label='Excelente', description='Atendimento perfeito!', value='5', emoji='🌟'),
            discord.SelectOption(label='Muito Bom', description='Fiquei bem satisfeito.', value='4', emoji='⭐'),
            discord.SelectOption(label='Bom', description='Atendimento ok.', value='3', emoji='👍'),
            discord.SelectOption(label='Regular', description='Poderia ser melhor.', value='2', emoji='😐'),
            discord.SelectOption(label='Ruim', description='Não fiquei satisfeito.', value='1', emoji='👎'),
            discord.SelectOption(label='Péssimo', description='Experiência muito ruim.', value='0', emoji='💢'),
        ]
        super().__init__(placeholder='⭐ Selecione sua nota...', options=options)

    async def callback(self, interaction: discord.Interaction):
        stars = int(self.values[0])
        modal = ReviewModal(self.channel_id, self.staff_id, stars)
        await interaction.response.send_modal(modal)


class StarView(View):
    def __init__(self, channel_id, staff_id):
        super().__init__(timeout=300)
        self.add_item(StarSelect(channel_id, staff_id))


# ── BOTÕES DO TICKET ────────────────────────────────────────────────
class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Assumir', style=discord.ButtonStyle.success, custom_id='ticket_claim', emoji='✋')
    async def claim(self, interaction: discord.Interaction, button: Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        member = interaction.user

        has_perm = any(r.position >= staff_role.position for r in member.roles if r != interaction.guild.default_role)
        if not has_perm:
            return await interaction.response.send_message(
                '❌ **Sem permissão!**\nApenas a equipe pode assumir tickets.',
                ephemeral=True
            )

        ticket = open_tickets.get(interaction.channel.id)
        if ticket:
            ticket['staff_id'] = interaction.user.id

        embed = interaction.message.embeds[0]
        embed.add_field(name='✋ Atendente', value=interaction.user.mention, inline=True)
        embed.color = 0x3498DB

        button.disabled = True
        button.label = 'Assumido'
        button.style = discord.ButtonStyle.secondary
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message(
            f'✅ {interaction.user.mention} assumiu este ticket!',
        )

    @discord.ui.button(label='Fechar', style=discord.ButtonStyle.danger, custom_id='ticket_close', emoji='🔒')
    async def close(self, interaction: discord.Interaction, button: Button):
        ticket = open_tickets.get(interaction.channel.id)
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)

        is_staff = any(r.position >= staff_role.position for r in interaction.user.roles if r != interaction.guild.default_role)
        is_owner = ticket and interaction.user.id == ticket.get('user_id')

        if not is_staff and not is_owner:
            return await interaction.response.send_message(
                '❌ **Sem permissão!**\nApenas o dono do ticket ou a equipe pode fechar.',
                ephemeral=True
            )

        if ticket:
            user = bot.get_user(ticket['user_id'])
            staff_id = ticket.get('staff_id')

            review_embed = discord.Embed(
                title='⭐ Como foi seu atendimento?',
                description=(
                    '> Seu ticket foi encerrado!\n\n'
                    'Gostaríamos de saber sua opinião sobre o atendimento recebido.\n'
                    'Selecione uma nota abaixo e deixe seu comentário.'
                ),
                color=0xF1C40F
            )
            review_embed.set_footer(text='Sua avaliação é muito importante para nós!')
            view = StarView(interaction.channel.id, staff_id)

            sent = False
            if user:
                try:
                    await user.send(embed=review_embed, view=view)
                    sent = True
                except Exception:
                    pass
            if not sent:
                await interaction.channel.send(
                    content=f'<@{ticket["user_id"]}>',
                    embed=review_embed,
                    view=view
                )

        open_tickets.pop(interaction.channel.id, None)

        close_embed = discord.Embed(
            title='🔒 Ticket Encerrado',
            description='Este ticket foi fechado.\nO canal será deletado em **5 segundos**.',
            color=0xE74C3C
        )
        await interaction.response.defer()
        await interaction.channel.send(embed=close_embed)
        await asyncio.sleep(5)
        await interaction.channel.delete()


# ── DROPDOWN DO PAINEL ──────────────────────────────────────────────
class TicketSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label='Denúncia',
                description='Reporte usuários que quebram as regras',
                value='denuncia',
                emoji='💬'
            ),
            discord.SelectOption(
                label='Bugs',
                description='Relate problemas ou erros no servidor',
                value='bugs',
                emoji='🐞'
            ),
            discord.SelectOption(
                label='Compra',
                description='Dúvidas ou pedidos sobre compras',
                value='compra',
                emoji='💰'
            ),
        ]
        super().__init__(
            placeholder='🎫 Selecione o motivo do ticket...',
            options=options,
            custom_id='ticket_select'
        )

    async def callback(self, interaction: discord.Interaction):
        type_labels = {
            'denuncia': ('💬 Denúncia', 0xE74C3C),
            'bugs': ('🐞 Bug Report', 0xF39C12),
            'compra': ('💰 Compra', 0x2ECC71)
        }
        label, color = type_labels[self.values[0]]

        await interaction.response.defer(ephemeral=True)

        existing = next(
            (c for c in interaction.guild.text_channels if getattr(c, 'topic', None) == f'Ticket de {interaction.user.id} | Tipo: {self.values[0]}'),
            None
        )
        if existing:
            return await interaction.followup.send(
                f'⚠️ **Você já tem um ticket aberto!**\nAcesse: {existing.mention}',
                ephemeral=True
            )

        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }

        safe_name = ''.join(c for c in interaction.user.name.lower() if c.isalnum())[:20]
        channel = await interaction.guild.create_text_channel(
            name=f'🎫┃{safe_name}',
            topic=f'Ticket de {interaction.user.id} | Tipo: {self.values[0]}',
            overwrites=overwrites
        )

        open_tickets[channel.id] = {'user_id': interaction.user.id, 'staff_id': None, 'type': self.values[0]}

        embed = discord.Embed(
            title=f'{label}',
            description=(
                f'Olá, {interaction.user.mention}! 👋\n\n'
                f'**Bem-vindo ao seu ticket!**\n'
                f'> Nossa equipe irá atendê-lo em breve.\n\n'
                f'📌 **Dicas:**\n'
                f'• Descreva seu problema com detalhes\n'
                f'• Envie prints se necessário\n'
                f'• Aguarde um membro da equipe'
            ),
            color=color
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name='👤 Usuário', value=interaction.user.mention, inline=True)
        embed.add_field(name='📋 Tipo', value=label, inline=True)
        embed.set_footer(text=f'Ticket • {interaction.guild.name}', icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.timestamp = discord.utils.utcnow()

        await channel.send(
            content=f'||<@&{STAFF_ROLE_ID}>||',
            embed=embed,
            view=TicketButtons()
        )

        await interaction.followup.send(
            f'✅ **Ticket criado com sucesso!**\n📂 Acesse: {channel.mention}',
            ephemeral=True
        )


class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ── ON READY ────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    bot.add_view(TicketButtons())
    print(f'✅ Bot online como {bot.user}')

    channel = bot.get_channel(TICKET_PANEL_CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.delete()

        embed = discord.Embed(
            title='🎫  Central de Tickets',
            description=(
                '━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                '**Precisa de ajuda? Abra um ticket!**\n'
                'Selecione a categoria abaixo que melhor descreve sua solicitação.\n\n'
                '💬  **Denúncia**\n'
                '╰ Reporte usuários que estão quebrando as regras.\n\n'
                '🐞  **Bugs**\n'
                '╰ Encontrou um erro ou problema? Relate aqui.\n\n'
                '💰  **Compra**\n'
                '╰ Dúvidas ou pedidos sobre compras do painel adm.\n\n'
                '━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
                '*⏱️ Tempo médio de resposta: alguns minutos*'
            ),
            color=0x5865F2
        )
        embed.set_image(url='https://i.pinimg.com/1200x/de/ea/a9/deeaa9f78a7f3cd6f88ee987dc6484ea.jpg')
        if channel.guild.icon:
            embed.set_footer(text=channel.guild.name, icon_url=channel.guild.icon.url)
        embed.timestamp = discord.utils.utcnow()

        await channel.send(embed=embed, view=TicketView())
        print(f'✅ Painel enviado no canal #{channel.name}')
    else:
        print('❌ Canal do painel não encontrado!')


bot.run(TOKEN)