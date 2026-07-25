// Sample product data (in a real app, this would come from an API)
const products = [
    {
        id: 1,
        brand: "Philips",
        name: "Philips HD7431/20 Kahve Makinesi",
        image: "https://via.placeholder.com/300x200?text=Kahve+Makinesi",
        originalPrice: 299,
        discountedPrice: 249,
        discountPercent: 17,
        rating: 4.5,
        reviewCount: 128,
        category: "kahve"
    },
    {
        id: 2,
        brand: "Philips",
        name: "Philips Airfryer XXL",
        image: "https://via.placeholder.com/300x200?text=Airfryer",
        originalPrice: 1299,
        discountedPrice: 999,
        discountPercent: 23,
        rating: 4.7,
        reviewCount: 256,
        category: "airfryer"
    },
    {
        id: 3,
        brand: "Bosch",
        name: "Bosch ProMix Blender",
        image: "https://via.placeholder.com/300x200?text=Blender",
        originalPrice: 599,
        discountedPrice: 449,
        discountPercent: 25,
        rating: 4.3,
        reviewCount: 189,
        category: "blender"
    },
    {
        id: 4,
        brand: "Philips",
        name: "Philips Azur Ütü",
        image: "https://via.placeholder.com/300x200?text=Ütü",
        originalPrice: 399,
        discountedPrice: 299,
        discountPercent: 25,
        rating: 4.4,
        reviewCount: 142,
        category: "utu"
    },
    {
        id: 5,
        brand: "Philips",
        name: "Philips OneBlade Kişisel Bakım",
        image: "https://via.placeholder.com/300x200?text=Kişisel+Bakım",
        originalPrice: 249,
        discountedPrice: 199,
        discountPercent: 20,
        rating: 4.2,
        reviewCount: 97,
        category: "bakim"
    },
    {
        id: 6,
        brand: "DeLonghi",
        name: "DeLonghi Dedica Kahve Makinesi",
        image: "https://via.placeholder.com/300x200?text=Kahve+Makinesi",
        originalPrice: 899,
        discountedPrice: 699,
        discountPercent: 22,
        rating: 4.6,
        reviewCount: 203,
        category: "kahve"
    },
    {
        id: 7,
        brand: "Tefal",
        name: "Tefal Actifry Geniş Kapasiteli Airfryer",
        image: "https://via.placeholder.com/300x200?text=Airfryer",
        originalPrice: 1099,
        discountedPrice: 799,
        discountPercent: 27,
        rating: 4.5,
        reviewCount: 176,
        category: "airfryer"
    },
    {
        id: 8,
        brand: "Vitamix",
        name: "Vitamix Professional Blender",
        image: "https://via.placeholder.com/300x200?text=Blender",
        originalPrice: 2499,
        discountedPrice: 1999,
        discountPercent: 20,
        rating: 4.8,
        reportCount: 312,
        category: "blender"
    },
    {
        id: 9,
        brand: "Rowenta",
        name: "Rowenta Steam Force Ütü",
        image: "https://via.placeholder.com/300x200?text=Ütü",
        originalPrice: 499,
        discountedPrice: 399,
        discountPercent: 20,
        rating: 4.3,
        reportCount: 158,
        category: "utu"
    },
    {
        id: 10,
        brand: "Braun",
        name: "Braun Silk-épil 9 Kişisel Bakım",
        image: "https://via.placeholder.com/300x200?text=Kişisel+Bakım",
        originalPrice: 899,
        discountedPrice: 699,
        discountPercent: 22,
        rating: 4.4,
        reportCount: 203,
        category: "bakim"
    }
];

// DOM Elements
const productGrid = document.getElementById('product-grid');
const categoryFilter = document.getElementById('category-filter');
const sortFilter = document.getElementById('sort-filter');
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const cartCount = document.getElementById('cart-count');
const newsletterForm = document.getElementById('newsletter-form');

// Cart state
let cart = [];
let favorites = new Set(); // Store product IDs that are favorites

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    renderProducts(products);
    updateCartCount();
    updateFavoriteUI(); // Initialize favorite button states
    
    // Event listeners
    categoryFilter.addEventListener('change', filterProducts);
    sortFilter.addEventListener('change', sortProducts);
    searchBtn.addEventListener('click', searchProducts);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchProducts();
    });
    newsletterForm.addEventListener('submit', handleNewsletterSignup);
});

// Render products to the grid
function renderProducts(productsToShow) {
    productGrid.innerHTML = '';
    
    if (productsToShow.length === 0) {
        productGrid.innerHTML = '<p class="no-products">Ürün bulunamadı.</p>';
        return;
    }
    
    productsToShow.forEach(product => {
        const productCard = document.createElement('div');
        productCard.className = 'product-card';
        productCard.innerHTML = `
            <div class="product-image">
                <img src="${product.image}" alt="${product.name}">
                ${product.discountPercent > 0 ? `<span class="discount-badge">%${product.discountPercent}</span>` : ''}
            </div>
            <div class="product-info">
                <div class="product-brand">${product.brand}</div>
                <h3 class="product-title">${product.name}</h3>
                <div class="product-pricing">
                    ${product.originalPrice > product.discountedPrice ? 
                        `<span class="original-price">${product.originalPrice.toLocaleString()} TL</span>` : ''}
                    <span class="discounted-price">${product.discountedPrice.toLocaleString()} TL</span>
                </div>
                <div class="product-rating">
                    ${'★'.repeat(Math.floor(product.rating))}${product.rating % 1 >= 0.5 ? '½' : ''}
                    <span>(${product.reviewCount})</span>
                </div>
                <div class="product-actions">
                    <button class="favorite-btn" aria-label="Favorilere ekle" data-id="${product.id}">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                        </svg>
                    </button>
                    <button class="add-to-cart" data-id="${product.id}">
                        Sepete Ekle
                    </button>
                </div>
            </div>
        `;
        
        // Add event listeners to buttons
        const favoriteBtn = productCard.querySelector('.favorite-btn');
        const addToCartBtn = productCard.querySelector('.add-to-cart');