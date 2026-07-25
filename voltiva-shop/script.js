// Product data
const products = [
  {
    id: 1,
    name: "Voltiva CleanBot X2 Robot Süpürge",
    category: "Robot Süpürgeler",
    image: "https://via.placeholder.com/300x300?text=CleanBot+X2",
    oldPrice: 19999,
    price: 14999,
    discount: 25,
    rating: 4.5,
    reviews: 128,
    stock: "Stokta Var",
    isFavorite: false
  },
  {
    id: 2,
    name: "Voltiva Barista Pro Kahve Makinesi",
    category: "Kahve Makineleri",
    image: "https://via.placeholder.com/300x300?text=Barista+Pro",
    oldPrice: 18999,
    price: 12499,
    discount: 34,
    rating: 4.7,
    reviews: 205,
    stock: "Stokta Var",
    isFavorite: false
  },
  {
    id: 3,
    name: "Voltiva DualFry Airfryer",
    category: "Airfryer",
    image: "https://via.placeholder.com/300x300?text=DualFry+Airfryer",
    oldPrice: 9999,
    price: 6999,
    discount: 30,
    rating: 4.3,
    reviews: 87,
    stock: "Stokta Var",
    isFavorite: false
  },
  {
    id: 4,
    name: "Voltiva SteamMax Ütü",
    category: "Ütüler",
    image: "https://via.placeholder.com/300x300x300?text=SteamMax+%C3%9Ct%C3%BC",
    oldPrice: 6999,
    price: 4799,
    discount: 31,
    rating: 4.6,
    reviews: 154,
    stock: "Stokta Var",
    isFavorite: false
  },
  {
    id: 5,
    name: "Voltiva BlendGo Blender",
    category: "Blender ve Mikser",
    image: "https://via.placeholder.com/300x300?text=BlendGo+Blender",
    oldPrice: 3999,
    price: 2499,
    discount: 38,
    rating: 4.4,
    reviews: 93,
    stock: "Stokta Var",
    isFavorite: false
  },
  {
    id: 6,
    name: "Voltiva StylePro Saç Şekillendirici",
    category: "Kişisel Bakım",
    image: "https://via.placeholder.com/300x300?text=StylePro+Sa%C3%A7",
    oldPrice: 11999,
    price: 7999,
    discount: 33,
    rating: 4.2,
    reviews: 67,
    stock: "Stokta Var",
    isFavorite: false
  },
  {
    id: 7,
    name: "Voltiva Türk Kahvesi Makinesi",
    category: "Kahve Makineleri",
    image: "https://via.placeholder.com/300x300?text=T%C3%BCrk+Kahvesi+Makinesi",
    oldPrice: 3499,
    price: 2199,
    discount: 37,
    rating: 4.8,
    reviews: 210,
    stock: "Stokta Var",
    isFavorite": false
  },
  {
    id: 8,
    name: "Voltiva FlexVac Dikey Süpürge",
    category: "Robot Süpürgeler",
    image: "https://via.placeholder.com/300x300?text=FlexVac+Dikey",
    oldPrice: 12999,
    price: 8999,
    discount: 31,
    rating: 4.5,
    reviews: 112,
    stock: "Stokta Var",
    isFavorite: false
  }
];

// Fix typo in product 7
products[7].isFavorite = false;

// DOM Elements
const productGrid = document.getElementById('product-grid');
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const cartBtn = document.getElementById('cart-btn');
const cartCount = document.getElementById('cart-count');
const favBtn = document.getElementById('fav-btn');
const favCount = document.getElementBy = document.getElementById('fav-count');
const newsletterForm = document.getElementById('newsletter-form');
const newsletterInput = document.getElementById('newsletter-input');
const newsletterMessage = document.getElementById('newsletter-message');
const reviewsSlider = document.getElementById('reviews-slider');

// Cart state
'); 
let favorites = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  renderProducts(products);
  renderReviews();
  updateCartCount();
  updateFavCount();
  
  // Event listeners
  searchBtn.addEventListener('click', handleSearch);
  searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSearch();
  });
  
  cartBtn.addEventListener('click', toggleMiniCart);
  favBtn.addEventListener('click', toggleFavorites);
  
  newsletterForm.addEventListener('submit', handleNewsletter);
  
  // Close mini cart when clicking outside
  document.addEventListener('click', (e) => {
    const miniCart = document.querySelector('.mini-cart');
    if (miniCart && !cartBtn.contains(e.target) && !miniCart.contains(e.target)) {
      miniCart.remove();
    }
  });
});

// Render products
function renderProducts(productList) {
  productGrid.innerHTML = '';
  
  productList.forEach(product => {
    const productCard = document.createElement('article');
    productCard.className = 'product-card';
    productCard.innerHTML = `
      <img src="${product.image}" alt="${product.name}">
      <div class="product-info">
        <span class="category">${product.category}</span>
        <h3 class="product-title">${product.name}</h3>
        <div class="price-info">
          <span class="current-price">${product.price.toLocaleString('tr-TR')} TL</span>
          ${product.oldPrice ? `<span class="old-price">${product.oldPrice.toLocaleString('tr-TR')} TL</span>` : ''}
          ${product.discount ? `<span class="discount-badge">%${product.discount} İndirim</span>` : ''}
        </div>
        <div class="rating">
          ${'★'.repeat(Math.floor(product.rating))}${'☆'.repeat(5 - Math.floor(product.rating))}
          <span>(${product.reviews})</span>
        </div>
        <p class="stock">${product.stock}</p>
        <div class="product-actions">
          <button class="icon-btn fav-btn" data-id="${product.id}" aria-label="${product.isFavorite ? 'Favoriden kaldır' : 'Favorilere ekle'}">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" class="bi bi-heart${product.isFavorite ? '-fill' : ''}" viewBox="0 0 16 16"><path d="m8 2.748-.717-.737C5.6.281 2.514.878 1.4 3.053c-.523 1.023-.641 2.5.314 4.385.92 1.815 2.834 3.952 6.286 6.374 3.452-2.2 5.365-4.559 6.286-6.374.955-1.886.836-3.362.314-4.385C13.486.878 10.4.281 8.717 2.748zM8 15c-7.33 0-12.604-6.027-12.604-13.445 0-.425.034-.838.102-1.241l-.003-.266a32.484 32.484 0 0 1-.034-.022l-.002-.018c-.015-.123-.046-.332-.124-.517C3.31.193 4.665.08 6.05.183c1.396.103 2.85.383 4.013.776 1.165.393 2.382.85.383 4.013.776 1.165.393 2.382.82 3.462 1.33 1.08-.51 2.22-.995 3.19-1.592.97-.597 1.913-1.18 2.73-1.755.815-.575 1.64-1.09 2.322-1.553.682-.463 1.33-.88 1.835-1.23.505-.35.976-.639 1.38-.865.404-.226.78-.418 1.09-.571.31-.153.586-.282.81-.384.224-.102.414-.186.57-.246.156-.06.283-.11.386-.149.093-.039.176-.074.246-.097.123-.023.233-.045.33-.064.107-.019.203-.036.286-.05.083-.014.153-.026.21-.037.067-.011.124-.021.168-.031.044-.009.078-.016.101-.023.023-.004.036-.007.046-.01.013-.002.021-.004.028-.006.004-.001.006-.002.008-.003.001-.001.002-.001.003-.001z"/></svg>
          </button>
          <button class="btn add-to-cart" data-id="${product.id}">Sepete Ekle</button>
        </div>
      </div>
    `;
    productGrid.appendChild(productCard);
  });
  
  // Add event listeners to buttons
  document.querySelectorAll('.fav-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = parseInt(e.currentTarget.dataset.id);
      toggleFavorite(id);
    });
  });
  
  document.querySelectorAll('.add-to-cart').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = parseInt(e.currentTarget.dataset.id);
      addToCart(id);
    });
  });
}

// Search functionality
function handleSearch() {
  const query = searchInput.value.trim().toLowerCase();
  if (!query) {
    renderProducts(products);
    return;
  }
  
  const filtered = products.filter(p => 
    p.name.toLowerCase().includes(query) || 
    p.category.toLowerCase().includes(query)
  );
  
  renderProducts(filtered);
}

// Cart functionality
let cart = JSON.parse(localStorage.getItem('cart')) || [];

function addToCart(productId) {
  const product = products.find(p => p.id === productId);
  if (!product) return;
  
  const existingItem = cart.find(item => item.id === productId);
  if (existingItem) {
    existingItem.quantity += 1;
  } else {
    cart.push({ ...product, quantity: 1 });
  }
  
  saveCart();
  updateCartCount();
  showNotification(`${product.name} sepete eklendi!`);
  updateMiniCart();
}

function removeFromCart(productId) {
  cart = cart.filter(item => item.id !== productId);
  saveCart();
  updateCartCount();
  updateMiniCart();
}

function updateQuantity(productId, change) {
  const item = cart.find(item => item.id === productId);
  if (item) {
    item.quantity += change;
    if (item.quantity <= 0) {
      removeFromCart(productId);
    } else {
      saveCart();
      updateCartCount();
      updateMiniCart();
    }
  }
}

function saveCart() {
  localStorage.setItem('cart', JSON.stringify(cart));
}

function updateCartCount() {
  const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
  cartCount.textContent = totalItems;
  cartCount.style.display = totalItems > 0 ? 'block' : 'none';
}

// Mini cart
function toggleMiniCart() {
  // Remove existing if any
  const existing = document.querySelector('.mini-cart');
  if (existing) {
    existing.remove();
    return;
  }
  
  const miniCart = document.createElement('div');
  miniCart.className = 'mini-cart';
  
  let total = 0;
  let itemsCount = 0;
  
  cart.forEach(item => {
    total += item.price * item.quantity;
    itemsCount += item.quantity;
  });
  
  const freeShippingThreshold = 2000;
  const freeShipping = total >= freeShippingThreshold;
  const shippingCost = freeShipping ? 0 : 29; // Assuming 29 TL shipping
  
  miniCart.innerHTML = `
    <div class="mini-cart-header">
      <h3>Sepetim</h3>
      <button class="close-btn" aria-label="Sepeti kapat">&times;</button>
    </div>
    <div class="mini-cart-body">
      ${cart.length === 0 ? '<p>Sepetiniz boş.</p>' : cart.map(item => `
        <div class="cart-item">
          <img src="${item.image}" alt="${item.name}">
          <div>
            <h4>${item.name}</h4>
            <p>${item.price.toLocaleString('tr-TR')} TL × ${item.quantity}</p>
          </div>
          <div class="cart-item-actions">
            <button class="qty-btn" data-id="${item.id}" data-change="-1">-</button>
            <span class="quantity">${item.quantity}</span>
            <button class="qty-btn" data-id="${item.id}" data-change="1">+</button>
            <button class="remove-btn" data-id="${item.id}" aria-label="Ürünü kaldır">&times;</button>
          </div>
        </div>
      `).join('')}
    </div>
    <div class="mini-cart-footer">
      <div class="summary">
        <p>Ara Toplam: <span>${total.toLocaleString('tr-TR')} TL</span></p>
        <p>Kargo: <span>${shippingCost.toLocaleString('tr-TR')} TL${freeShipping ? ' (Ücretsiz)' : ''}</span></p>
        <p class="total">Toplam: <span>${(total + shippingCost).toLocaleString('tr-TR')} TL</span></p>
      </div>
      ${cart.length > 0 ? `<button class="btn primary checkout-btn">Ödemeyi Tamamla</button>` : ''}
    </div>
  `;
  
  document.body.appendChild(miniCart);
  
  // Event listeners for mini cart
  miniCart.querySelector('.close-btn').addEventListener('click', () => miniCart.remove());
  miniCart.querySelectorAll('.qty-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = parseInt(e.currentTarget.dataset.id);
      const change = parseInt(e.currentTarget.dataset.change);
      updateQuantity(id, change);
    });
  });
  
  miniCart.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = parseInt(e.currentTarget.dataset.id);
      removeFromCart(id);
    });
  });
  
  miniCart.querySelector('.checkout-btn').addEventListener('click', () => {
    alert('Ödeme sayfasına yönlendiriliyor...');
    // In a real app, redirect to checkout page
  });
}

// Favorites functionality
function toggleFavorite(productId) {
  const product = products.find(p => p.id === productId);
  if (!product) return;
  
  product.isFavorite = !product.isFavorite;
  
  const index = favorites.indexOf(productId);
  if (product.isFavorite) {
    if (index === -1) favorites.push(productId);
  } else {
    if (index !== -1) favorites.splice(index, 1);
  }
  
  localStorage.setItem('favorites', JSON.stringify(favorites));
  updateFavCount();
  renderProducts(getFilteredProducts()); // Re-render to update heart icons
}

function updateFavCount() {
  favCountBy.textContent = favorites.length;
  favCountBy.style.display = favorites.length > 0 ? 'block' : 'none';
}

// Newsletter
function handleNewsletter(e) {
  e.preventDefault();
  const email = newsletterInput.value.trim();
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  
  if (!email) {
    showMessage(newsletterMessage, 'Lütfen e-posta adresinizi girin.', 'error');
    return;
  }
  
  if (!emailRegex.test(email)) {
    showMessage(newsletterMessage, 'Lütfen geçerli bir e-posta adresi girin.', 'error');
    return;
  }
  
  // Simulate successful subscription
  showMessage(newsletterMessage, 'Abone olundu! Teşekkür ederiz.', 'success');
  newsletterForm.reset();
}

function showMessage(element, text, type) {
  element.textContent = text;
  element.className = `message ${type}`;
  element.style.display = 'block';
  
  setTimeout(() => {
    element.style.display = 'none';
  }, 3000);
}

// Reviews slider (simple auto-scroll)
function renderReviews() {
  const reviews = [
    {
      name: "Ahmet Yılmaz",
      rating: 5,
      text: "Voltiva CleanBot X2 gerçekten işimi gördü. Ev temizliği çok daha kolaylaştı.",
      date: "15 Nisan 2024"
    },
    {
      name: "Elif Demir",
      rating: 4,
      text: "Barista Pro kahve makinesi, kahve calidadı harika. Tavsiye ederim.",
      date: "10 Nisan 2024"
    },
    {
      name: "Mehmet Kaya",
      rating: 5,
      text: "Airfryer ile sağlıklı yemekler yapıyoruz. Çok memnun kaldık.",
      date: "5 Nisan 2024"
    }
  ];
  
  reviewsSlider.innerHTML = '';
  
  reviews.forEach(review => {
    const reviewCard = document.createElement('div');
    reviewCard.className = 'review-card';
    reviewCard.innerHTML = `
      <div class="review-header">
        <h4>${review.name}</h4>
        <div class="rating">${'★'.repeat(review.rating)}${'☆'.repeat(5 - review.rating)}</div>
      </div>
      <p class="review-text">${review.text}</p>
      <p class="review-date">${review.date}</p>
    `;
    reviewsSlider.appendChild(reviewCard);
  });
  
  // Simple auto-scroll
  let scrollIndex = 0;
  setInterval(() => {
    scrollIndex = (scrollIndex + 1) % reviews.length;
    reviewsSlider.scrollTo({
      left: reviewCard.offsetWidth * scrollIndex,
      behavior: 'smooth'
    });
  }, 5000);
}

// Helper functions
function getFilteredProducts() {
  const query = searchInput.value.trim().toLowerCase();
  if (!query) return products;
  
  return products.filter(p => 
    p.name.toLowerCase().includes(query) || 
    p.category.toLowerCase().includes(query)
  );
}

function showNotification(message) {
  // Remove any existing notification
  const existing = document.querySelector('.notification');
  if (existing) {
    existing.remove();
  }
  
  const notification = document.createElement('div');
  notification.className = 'notification';
  notification.textContent = message;
  
  document.body.appendChild(notification);
  
  // Remove after 3 seconds
  setTimeout(() => {
    notification.remove();
  }, 3000);
}

// Initialize favorites from localStorage
document.addEventListener('DOMContentLoaded', () => {
  const savedFavorites = localStorage.getItem('favorites');
  if (savedFavorites) {
    favorites = JSON.parse(savedFavorites);
    // Update product favorite status
    favorites.forEach(id => {
      const product = products.find(p => p.id === id);
      if (product) product.isFavorite = true;
    });
  }
  
  updateFavCount();
});