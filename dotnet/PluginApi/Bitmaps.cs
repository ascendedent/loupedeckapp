// Images: what a plugin draws on a key, and how it builds one.
//
// Written from Logitech's public documentation and sample plugins, and from
// the shapes compiled plugins reference (dotnet/tools/ApiScan.cs). The drawing
// itself is behind Canvas (below): System.Drawing on Mono (libgdiplus),
// SkiaSharp on .NET 8/10, where System.Drawing does not exist off Windows. An
// image travels to the app as PNG bytes.
namespace Loupedeck
{
    using System;
    using System.IO;

    // Key image sizes a plugin can be asked for. The CT and Live draw 90 px
    // keys; 60 is the older, smaller size.
    public enum PluginImageSize
    {
        None = 0,
        Width60 = 1,
        Width90 = 2,
        Width116 = 3,
    }

    public enum BitmapRotation
    {
        None = 0,
        Rotate90 = 1,
        Rotate180 = 2,
        Rotate270 = 3,
    }

    public struct BitmapColor
    {
        public BitmapColor(Int32 red, Int32 green, Int32 blue) : this(red, green, blue, 255) { }

        public BitmapColor(Int32 red, Int32 green, Int32 blue, Int32 alpha)
        {
            this.R = Clamp(red);
            this.G = Clamp(green);
            this.B = Clamp(blue);
            this.A = Clamp(alpha);
        }

        public BitmapColor(BitmapColor color, Int32 alpha) : this(color.R, color.G, color.B, alpha) { }

        public Int32 R { get; private set; }
        public Int32 G { get; private set; }
        public Int32 B { get; private set; }
        public Int32 A { get; private set; }

        public static BitmapColor Black { get { return new BitmapColor(0, 0, 0); } }
        public static BitmapColor White { get { return new BitmapColor(255, 255, 255); } }
        public static BitmapColor Red { get { return new BitmapColor(255, 0, 0); } }
        public static BitmapColor Green { get { return new BitmapColor(0, 255, 0); } }
        public static BitmapColor Blue { get { return new BitmapColor(0, 0, 255); } }
        public static BitmapColor Transparent { get { return new BitmapColor(0, 0, 0, 0); } }

        public static Boolean operator ==(BitmapColor a, BitmapColor b)
        {
            return a.R == b.R && a.G == b.G && a.B == b.B && a.A == b.A;
        }

        public static Boolean operator !=(BitmapColor a, BitmapColor b) { return !(a == b); }

        public override Boolean Equals(Object obj) { return obj is BitmapColor && (BitmapColor)obj == this; }

        public override Int32 GetHashCode() { return (this.A << 24) | (this.R << 16) | (this.G << 8) | this.B; }

        public override String ToString() { return String.Format("#{0:X2}{1:X2}{2:X2}{3:X2}", this.R, this.G, this.B, this.A); }

        private static Int32 Clamp(Int32 v) { return v < 0 ? 0 : (v > 255 ? 255 : v); }
    }

    // Compiled plugins reference Width and Resize through this base.
    public abstract class BitmapImageBase : IDisposable
    {
        protected Byte[] _bytes;

        internal BitmapImageBase(Byte[] bytes) { this._bytes = bytes; }

        public Int32 Width { get { return Canvas.ImageSize(this._bytes)[0]; } }

        public Int32 Height { get { return Canvas.ImageSize(this._bytes)[1]; } }

        // In place: compiled plugins ignore the result and use the image.
        internal Boolean ResizeTo(Int32 width, Int32 height)
        {
            try
            {
                using (var c = Canvas.Create(Math.Max(1, width), Math.Max(1, height)))
                {
                    c.Clear(BitmapColor.Transparent);
                    c.DrawImage(this._bytes, 0, 0, width, height, BitmapRotation.None);
                    this._bytes = c.ToPng();
                }
                return true;
            }
            catch (Exception) { return false; }
        }

        public virtual void Dispose() { }
    }

    // An image, held as the encoded bytes it came as (PNG, JPEG, SVG...).
    public class BitmapImage : BitmapImageBase
    {
        internal BitmapImage(Byte[] bytes) : base(bytes) { }

        internal Byte[] Bytes { get { return this._bytes; } }

        // SVG is passed through as it is: the app renders it (Qt), where the
        // drawing libraries here cannot.
        internal Boolean IsSvg
        {
            get
            {
                var n = Math.Min(this._bytes.Length, 512);
                var head = System.Text.Encoding.UTF8.GetString(this._bytes, 0, n);
                return head.Contains("<svg");
            }
        }

        public static BitmapImage FromArray(Byte[] array) { return array == null ? null : new BitmapImage(array); }

        public static BitmapImage FromBase64String(String base64)
        {
            return String.IsNullOrEmpty(base64) ? null : new BitmapImage(Convert.FromBase64String(base64));
        }

        public static BitmapImage FromFile(String filePath) { return FromArray(File.ReadAllBytes(filePath)); }

        public static BitmapImage FromResource(System.Reflection.Assembly assembly, String resourceName)
        {
            return assembly.ReadImage(resourceName);
        }

        public Byte[] ToArray() { return (Byte[])this._bytes.Clone(); }

        public String ToBase64String() { return Convert.ToBase64String(this._bytes); }

        // What the app receives: a data: URL, PNG unless the image is SVG.
        internal String ToDataUrl()
        {
            if (this.IsSvg) return "data:image/svg+xml;base64," + Convert.ToBase64String(this._bytes);
            return "data:image/png;base64," + Convert.ToBase64String(Canvas.ToPng(this._bytes));
        }
    }

    public static class BitmapImageExtensions
    {
        public static BitmapImage ToImage(this Byte[] array) { return BitmapImage.FromArray(array); }

        public static Boolean Resize(this BitmapImageBase image, Int32 width, Int32 height)
        {
            return image != null && image.ResizeTo(width, height);
        }

        public static Boolean Resize(this BitmapImageBase image, PluginImageSize imageSize)
        {
            var px = BitmapBuilder.SizeOf(imageSize);
            return Resize(image, px, px);
        }
    }

    public class BitmapBuilder : IDisposable
    {
        private readonly Canvas _canvas;

        public BitmapBuilder(PluginImageSize imageSize)
            : this(SizeOf(imageSize), SizeOf(imageSize)) { }

        public BitmapBuilder(Int32 width, Int32 height)
        {
            this._canvas = Canvas.Create(Math.Max(1, width), Math.Max(1, height));
            this._canvas.Clear(BitmapColor.Black);
        }

        public BitmapBuilder(BitmapImage image)
        {
            this._canvas = Canvas.FromImage(image.Bytes);
        }

        internal static Int32 SizeOf(PluginImageSize size)
        {
            switch (size)
            {
                case PluginImageSize.Width60: return 60;
                case PluginImageSize.Width116: return 116;
                default: return 90;
            }
        }

        public Int32 Width { get { return this._canvas.Width; } }

        public Int32 Height { get { return this._canvas.Height; } }

        public void Clear(BitmapColor color) { this._canvas.Clear(color); }

        public void SetBackgroundImage(BitmapImage image)
        {
            if (image != null) this._canvas.DrawImage(image.Bytes, 0, 0, this.Width, this.Height, BitmapRotation.None);
        }

        public void DrawImage(BitmapImage image) { this.DrawImage(image, 0, 0, this.Width, this.Height); }

        public void DrawImage(BitmapImage image, Int32 x, Int32 y) { this.DrawImage(image, x, y, BitmapRotation.None); }

        public void DrawImage(BitmapImage image, Int32 x, Int32 y, BitmapRotation rotation)
        {
            if (image != null) this._canvas.DrawImage(image.Bytes, x, y, -1, -1, rotation);
        }

        public void DrawImage(BitmapImage image, Int32 x, Int32 y, Int32 width, Int32 height)
        {
            if (image != null) this._canvas.DrawImage(image.Bytes, x, y, width, height, BitmapRotation.None);
        }

        public void FillRectangle(Int32 x, Int32 y, Int32 width, Int32 height, BitmapColor color)
        {
            this._canvas.FillRectangle(x, y, width, height, color);
        }

        public void DrawRectangle(Int32 x, Int32 y, Int32 width, Int32 height, BitmapColor color)
        {
            this._canvas.DrawRectangle(x, y, width, height, color);
        }

        public void DrawLine(Int32 x1, Int32 y1, Int32 x2, Int32 y2, BitmapColor color, Single thickness = 1)
        {
            this._canvas.DrawLine(x1, y1, x2, y2, color, thickness);
        }

        public void FillCircle(Int32 x, Int32 y, Int32 radius, BitmapColor color)
        {
            this._canvas.FillCircle(x, y, radius, color);
        }

        public void FillCircle(Single x, Single y, Single radius, BitmapColor color)
        {
            this._canvas.FillCircle((Int32)Math.Round(x), (Int32)Math.Round(y), (Int32)Math.Round(radius), color);
        }

        // Move the origin for what is drawn next, and put it back.
        public void Translate(Single dx, Single dy) { this._canvas.Translate(dx, dy); }

        public void ResetMatrix() { this._canvas.ResetMatrix(); }

        // The whole key, centred: the common case.
        public void DrawText(String text) { this.DrawText(text, null, 0, 0, 0); }

        public void DrawText(String text, BitmapColor color) { this.DrawText(text, (BitmapColor?)color, 0, 0, 0); }

        public void DrawText(String text, BitmapColor color, Int32 fontSize) { this.DrawText(text, (BitmapColor?)color, fontSize, 0, 0); }

        public void DrawText(String text, BitmapColor? color, Int32 fontSize, Int32 lineHeight, Int32 lineSpacing)
        {
            this.DrawText(text, 0, 0, this.Width, this.Height, color, fontSize, lineHeight, lineSpacing);
        }

        public void DrawText(String text, Int32 x, Int32 y, Int32 width, Int32 height)
        {
            this.DrawText(text, x, y, width, height, null, 0, 0, 0);
        }

        public void DrawText(String text, Int32 x, Int32 y, Int32 width, Int32 height, BitmapColor? color = null,
                             Int32 fontSize = 0, Int32 lineHeight = 0, Int32 lineSpacing = 0)
        {
            if (String.IsNullOrEmpty(text)) return;
            var size = fontSize > 0 ? fontSize : AutoFontSize(text, width, height);
            this._canvas.DrawText(text, x, y, width, height, color ?? BitmapColor.White, size);
        }

        // Large enough to read, small enough that a longer name still fits.
        private static Int32 AutoFontSize(String text, Int32 width, Int32 height)
        {
            var longest = 0;
            foreach (var line in text.Split('\n'))
                longest = Math.Max(longest, line.Length);
            var byWidth = longest > 0 ? (Int32)(width * 1.6 / longest) : height;
            var lines = text.Split('\n').Length;
            var byHeight = height / (lines + 1);
            return Math.Max(9, Math.Min(Math.Min(byWidth, byHeight), height / 3));
        }

        public BitmapImage ToImage() { return new BitmapImage(this._canvas.ToPng()); }

        public void Dispose() { this._canvas.Dispose(); }
    }

    // One drawing surface. Each runtime supplies Create/FromImage/ImageSize/
    // ToPng and an implementation (Drawing.Gdi.cs, Drawing.Skia.cs).
    internal abstract partial class Canvas : IDisposable
    {
        internal abstract Int32 Width { get; }
        internal abstract Int32 Height { get; }
        internal abstract void Clear(BitmapColor color);
        internal abstract void FillRectangle(Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color);
        internal abstract void DrawRectangle(Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color);
        internal abstract void DrawLine(Int32 x1, Int32 y1, Int32 x2, Int32 y2, BitmapColor color, Single thickness);
        internal abstract void FillCircle(Int32 x, Int32 y, Int32 radius, BitmapColor color);
        // width/height of -1: the image's own size.
        internal abstract void DrawImage(Byte[] image, Int32 x, Int32 y, Int32 w, Int32 h, BitmapRotation rotation);
        internal abstract void DrawText(String text, Int32 x, Int32 y, Int32 w, Int32 h, BitmapColor color, Int32 size);
        internal abstract void Translate(Single dx, Single dy);
        internal abstract void ResetMatrix();
        internal abstract Byte[] ToPng();
        public abstract void Dispose();
    }
}
