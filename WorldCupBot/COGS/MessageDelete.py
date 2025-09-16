import discord
from discord.ext import commands


class MessageManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @commands.command(name="delete", help="Deletes a message sent by the bot using its message ID.")
    @commands.is_owner()
    async def delete_bot_message(self, ctx: commands.Context, message_id: int):
        """Deletes a message sent by the bot given the message ID."""
        try:
            await ctx.message.delete()
            # Fetch the message object using the ID
            message = await ctx.channel.fetch_message(message_id)

            # Check if the message was sent by the bot
            if message.author.id == self.bot.user.id:
                await message.delete()
                await ctx.send(f"Message with ID {message_id} has been deleted.", delete_after=1)
            else:
                await ctx.send("I can only delete messages sent by myself.", delete_after=1)

        except discord.NotFound:
            await ctx.send("Message not found. Please provide a valid message ID.", delete_after=1)
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete that message.", delete_after=1)
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred: {e}", delete_after=1)
            
            
    @commands.command()
    async def purge(self, ctx, amount: int):
        """Delete a number of messages in the current channel."""
        if amount < 1:
            await ctx.send("Amount must be at least 1.", delete_after=5)
            return
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"Deleted {len(deleted)} messages.", delete_after=5)


async def setup(bot):
    await bot.add_cog(MessageManager(bot))
